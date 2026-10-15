// Browser checks against the real read-only viewer: ledger_app.LedgerHandler served over HTTP
// by tests/viewer_fixture_server.py with FakeLedger/FakeHistory (fake data, no database).
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', '..');
const shots = path.join(root, 'test-results', 'viewer');
const VIEWPORTS = {desktop: {width: 1280, height: 900}, mobile: {width: 390, height: 844}};
const AS_OF = 'as_of=2026-10-15';
const CUSTOMER = 'name=A%20%26%20B';

function pythonCommand() {
  if (process.env.WEBDEBIT_PYTHON) return process.env.WEBDEBIT_PYTHON;
  const venv = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  if (fs.existsSync(venv)) return venv;
  return process.platform === 'win32' ? 'python' : 'python3';
}

let server = null;
let browser = null;
let ports = null;
let serverLog = '';

function startServer() {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonCommand(), ['-I', path.join(__dirname, 'viewer_fixture_server.py')], {
      cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
    });
    server = child;
    let out = '';
    const timer = setTimeout(() => reject(new Error(`viewer fixture server not ready in 20s: ${serverLog}`)), 20000);
    child.stderr.on('data', chunk => { serverLog += chunk; });
    child.stdout.on('data', chunk => {
      out += chunk;
      const line = out.split('\n')[0];
      if (!out.includes('\n')) return;
      clearTimeout(timer);
      try { resolve(JSON.parse(line)); } catch (error) { reject(error); }
    });
    child.on('error', error => { clearTimeout(timer); reject(error); });
    child.on('exit', code => { clearTimeout(timer); if (!ports) reject(new Error(`server exited ${code}: ${serverLog}`)); });
  });
}

async function stopServer() {
  const child = server;
  server = null;
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.stdin.end();
  const timer = setTimeout(() => child.kill(), 5000);
  await exited;
  clearTimeout(timer);
}

// Safety net if the test process dies before the hooks run.
process.on('exit', () => { if (server && server.exitCode === null) server.kill(); });

before(async () => {
  fs.mkdirSync(shots, {recursive: true});
  try {
    ports = await startServer();
    browser = await chromium.launch({headless: true});
  } catch (error) {
    await teardown();
    throw error;
  }
});

async function teardown() {
  try { if (browser) await browser.close(); } finally { browser = null; await stopServer(); }
}

after(teardown);

function url(scenario, route) {
  return `http://127.0.0.1:${ports[scenario]}${route}`;
}

async function withPage(viewport, fn) {
  const context = await browser.newContext({viewport: VIEWPORTS[viewport], locale: 'vi-VN'});
  try {
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await fn(page);
    assert.deepEqual(errors.filter(text => !/Failed to load resource/.test(text)), []);
  } finally {
    await context.close();
  }
}

async function openDetails(page) {
  for (const summary of await page.locator('main details > summary').all()) {
    if (!(await summary.evaluate(el => el.parentElement.open))) await summary.click();
  }
}

async function noPageOverflow(page, label) {
  const sizes = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth,
    body: document.body.scrollWidth}));
  assert.ok(sizes.scroll <= sizes.client, `${label}: page scrolls horizontally ${JSON.stringify(sizes)}`);
  assert.ok(sizes.body <= sizes.client, `${label}: body wider than viewport ${JSON.stringify(sizes)}`);
}

for (const viewport of Object.keys(VIEWPORTS)) {
  test(`${viewport}: source warning sits beside the balance on overview, customer and period`, () => withPage(viewport, async page => {
    await page.goto(url('default', `/?${AS_OF}`));
    const total = page.locator('.overview-summary');
    const warning = page.locator('.overview-summary + .source-warning');
    assert.match(await total.innerText(), /Tổng còn nợ mọi kỳ\s+100 ₫/);
    assert.match(await warning.innerText(), /53 ngoại lệ/);
    assert.equal(await warning.locator('a').getAttribute('href'), '/exceptions');
    const a = await total.boundingBox();
    const b = await warning.boundingBox();
    assert.ok(b.y >= a.y + a.height - 1 && b.y - (a.y + a.height) < 120, 'warning follows the total directly');

    await page.goto(url('default', `/customer?${CUSTOMER}&${AS_OF}`));
    const balance = page.locator('.customer-balance');
    const customerWarning = page.locator('.source-warning').first();
    assert.match(await balance.innerText(), /Tổng còn nợ/);
    assert.match(await customerWarning.innerText(), /Ngoại lệ khách \(mọi kỳ\)/);
    const c = await balance.boundingBox();
    const d = await customerWarning.boundingBox();
    assert.ok(d.y >= c.y && d.y - (c.y + c.height) < 160, 'customer warning is next to the balance');

    await page.goto(url('default', `/period?${CUSTOMER}&period=2026-10&${AS_OF}`));
    assert.match(await page.locator('main').innerText(), /Ngoại lệ/);
    await page.screenshot({path: path.join(shots, `period-${viewport}.png`)});
  }));

  test(`${viewport}: /exceptions filters, paginates and keeps safe source links`, () => withPage(viewport, async page => {
    await page.goto(url('default', '/exceptions'));
    assert.equal(await page.locator('.exception-table tbody tr').count(), 50);
    assert.match(await page.locator('.pager').innerText(), /Trang 1 \/ 2 · 53 kết quả · 50 mỗi trang/);
    // hostile fake detail stays text; javascript: source is not a link
    assert.equal(await page.locator('.exception-table img').count(), 0);
    assert.equal(await page.locator('a[href^="javascript:"]').count(), 0);
    assert.ok(await page.locator('.exception-table td:has-text("<img src=x")').count() >= 1);
    assert.match(await page.locator('.exception-table').innerText(), /Liên kết nguồn không hợp lệ/);
    await page.screenshot({path: path.join(shots, `exceptions-${viewport}.png`)});
    await noPageOverflow(page, `exceptions page 1 ${viewport}`);

    await page.getByRole('link', {name: 'Sau →'}).click();
    await page.waitForURL(/page=2/);
    assert.equal(await page.locator('.exception-table tbody tr').count(), 3);
    assert.match(await page.locator('.pager').innerText(), /Trang 2 \/ 2/);
    await page.getByRole('link', {name: '← Trước'}).click();
    await page.waitForURL(/page=1/);

    await page.selectOption('#code_mode', 'exact');
    await page.fill('#code', 'ZERO_TOTAL');
    await page.getByRole('button', {name: 'Lọc'}).click();
    await page.waitForURL(/code=ZERO_TOTAL/);
    assert.equal(await page.locator('.exception-table tbody tr').count(), 1);
    assert.match(await page.locator('.pager').innerText(), /1 kết quả/);
    const source = page.locator('.exception-table a.source-link');
    assert.equal(await source.count(), 1);
    assert.equal(await source.getAttribute('href'), 'https://docs.google.com/spreadsheets/d/fake/edit#gid=3&range=A4');

    await page.goto(url('default', '/exceptions?customer_mode=unclassified&period_mode=all&code_mode=all&page=1'));
    assert.equal(await page.locator('.exception-table tbody tr').count(), 1);
    assert.match(await page.locator('.exception-table').innerText(), /Chưa phân loại/);
  }));

  test(`${viewport}: NULL opening renders a dash, true zero renders 0 ₫`, () => withPage(viewport, async page => {
    await page.goto(url('null_opening', `/period?${CUSTOMER}&period=2026-11&${AS_OF}`));
    await openDetails(page);
    let text = await page.locator('main').innerText();
    assert.match(text, /Số mở sổ kỳ —/);
    assert.match(text, /Kỳ mới chưa có số mở sổ lịch sử/);
    assert.match(text, /không phải 0/);
    assert.doesNotMatch(text, /Số mở sổ kỳ 0 ₫/);
    await noPageOverflow(page, `null opening period ${viewport}`);

    await page.goto(url('null_opening', `/period?${CUSTOMER}&period=2026-10&${AS_OF}`));
    await openDetails(page);
    text = await page.locator('main').innerText();
    assert.match(text, /Số mở sổ kỳ 0 ₫/);
    assert.doesNotMatch(text, /Kỳ mới chưa có số mở sổ lịch sử/);

    await page.goto(url('null_opening', `/customer?${CUSTOMER}&${AS_OF}`));
    await openDetails(page);
    // Only the new period (opening NULL) is checked here; the other period has a true 0 opening.
    text = await page.locator('#period-2026-11').innerText();
    assert.match(text, /Kỳ mới không có số mở sổ lịch sử/);
    assert.match(text, /Số mở sổ kỳ —/);
    assert.doesNotMatch(text, /0 ₫ mở sổ kỳ/);
    assert.doesNotMatch(text, /Số mở sổ kỳ 0 ₫/);
    await noPageOverflow(page, `null opening customer ${viewport}`);
  }));

  test(`${viewport}: unreadable history says the exception check is unavailable, never zero`, () => withPage(viewport, async page => {
    const response = await page.goto(url('history_error', '/exceptions'));
    assert.equal(response.status(), 503);
    assert.equal(await page.locator('h1').innerText(), 'Chưa kiểm được ngoại lệ nguồn');
    assert.doesNotMatch(await page.locator('main').innerText(), /0 ngoại lệ/);

    const overview = await page.goto(url('history_error', `/?${AS_OF}`));
    assert.equal(overview.status(), 200);
    assert.match(await page.locator('.overview-summary').innerText(), /100 ₫/);
    const warning = page.locator('.source-warning.unavailable').first();
    assert.match(await warning.innerText(), /Chưa kiểm được ngoại lệ nguồn/);
    assert.equal(await page.locator('main > .source-warning.unavailable').count(), 1, 'one unavailable box above the table, not two');
    assert.doesNotMatch(await page.locator('main').innerText(), /\b0 ngoại lệ/);
    await page.screenshot({path: path.join(shots, `history-error-${viewport}.png`)});
  }));

  test(`${viewport}: no whole-page horizontal overflow on any viewer page`, () => withPage(viewport, async page => {
    const routes = [
      ['default', `/?${AS_OF}`], ['default', `/customer?${CUSTOMER}&${AS_OF}`],
      ['default', `/period?${CUSTOMER}&period=2026-10&${AS_OF}`],
      ['default', '/exceptions?customer_mode=all&period_mode=all&code_mode=all&page=2'],
      ['default', '/pending'], ['default', `/postings?${AS_OF}`],
      ['history_error', `/?${AS_OF}`], ['history_error', '/exceptions'],
    ];
    for (const [scenario, route] of routes) {
      await page.goto(url(scenario, route));
      await noPageOverflow(page, `${scenario} ${route} ${viewport}`);
    }
  }));
}

test('keyboard focus is visible and reaches the exception filters', () => withPage('desktop', async page => {
  await page.goto(url('default', `/?${AS_OF}`));
  await page.keyboard.press('Tab');
  const skip = page.locator('.skip');
  assert.equal(await skip.evaluate(el => el === document.activeElement), true);
  assert.ok((await skip.boundingBox()).x >= 0, 'skip link is on screen when focused');
  for (const label of [/^H\s+HTH/, /^Công nợ$/, /^Khoản chờ$/, /^Đã ghi sổ$/]) {
    await page.keyboard.press('Tab');
    assert.match(await page.locator(':focus').innerText(), label);
  }
  await page.keyboard.press('Tab'); // Ngoại lệ nguồn
  const focused = page.locator(':focus');
  assert.equal(await focused.innerText(), 'Ngoại lệ nguồn');
  const outline = await focused.evaluate(el => {
    const style = getComputedStyle(el);
    return {style: style.outlineStyle, width: parseFloat(style.outlineWidth)};
  });
  assert.notEqual(outline.style, 'none');
  assert.ok(outline.width >= 2, `focus outline width ${outline.width}`);
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/exceptions/);

  // Keyboard-only filter: type in the code box and submit with Enter.
  await page.selectOption('#code_mode', 'exact');
  await page.focus('#code');
  await page.keyboard.type('ZERO_TOTAL');
  await page.keyboard.press('Enter');
  await page.waitForURL(/code=ZERO_TOTAL/);
  assert.equal(await page.locator('.exception-table tbody tr').count(), 1);
  assert.equal(await page.locator('#code').inputValue(), 'ZERO_TOTAL');
}));
