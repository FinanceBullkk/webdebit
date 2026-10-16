const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const url=pathToFileURL(path.join(__dirname,'customer-ledger-workbench.html')).href;
async function withPage(fn){const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1600,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await fn(page);assert.deepEqual(errors,[]);}finally{await browser.close();}}

test('pending shipment notice follows filters, opens target, and never changes posted balance',async()=>withPage(async page=>{
  const before=await page.locator('#all-balance').innerText();
  assert.equal(await page.locator('#pending-shipment').isVisible(),false);
  await page.locator('#month-2026-03 [data-action="open-editor"]').click();
  await page.locator('[data-editor="2026-03"] [data-action="add"]').click();
  const row=page.locator('[data-editor="2026-03"] tbody tr').last();
  for(const [field,value] of Object.entries({date:'2026-03-12',container:'DEMO-PENDING',price:'1000000',otherFee:'0',tractionFee:'0',insuranceFee:'0'}))
    await row.locator(`[data-edit="${field}"]`).fill(value);
  await page.locator('[data-editor="2026-03"] [data-action="save"]').click();
  assert.equal(await page.locator('#pending-shipment').innerText(),'1 chuyến chờ duyệt');
  assert.equal(await page.locator('#all-balance').innerText(),before);
  assert.equal(await page.locator('#pending-price').innerText(),'1 chuyến chờ giá');
  await page.locator('#month-2026-03 > summary').click();
  await page.locator('#pending-shipment').click();
  assert.equal(await page.locator('#month-2026-03').evaluate(el=>el.open),true);
  const target=await page.locator('#pending-shipment').getAttribute('href');
  assert.equal(await page.locator(target).isVisible(),true);
  assert.match(await page.locator(target).innerText(),/Chờ duyệt/);
  await page.locator('#period').selectOption('2026-02');
  await page.locator('#filters button').click();
  assert.equal(await page.locator('#pending-shipment').isVisible(),false);
  assert.equal(await page.locator('#all-balance').innerText(),before);
  await page.locator('#period').selectOption('all');
  await page.locator('#as-of').fill('2026-03-11');
  await page.locator('#filters button').click();
  assert.equal(await page.locator('#pending-shipment').isVisible(),false);
  await page.locator('#as-of').fill('2026-04-30');
  await page.locator('#filters button').click();
  assert.equal(await page.locator('#pending-shipment').innerText(),'1 chuyến chờ duyệt');
  assert.equal(await page.locator('#all-balance').innerText(),before);
}));
test('interactive filter keeps all-period balance and opens only relevant period',async()=>withPage(async page=>{assert.equal(await page.locator('#all-balance').innerText(),'95,000,000');await page.locator('#period').selectOption('2026-02');await page.locator('#filters button').click();assert.equal(await page.locator('.month').count(),1);assert.equal(await page.locator('#all-balance').innerText(),'95,000,000');assert.equal(await page.locator('#visible-balance').innerText(),'30,000,000');}));
test('grid paste from a chosen cell keeps internal and trailing blanks',async()=>withPage(async page=>{await page.locator('#month-2026-03').locator('[data-action="open-editor"]').click();await page.locator('[data-editor="2026-03"] [data-action="add"]').click();const first=page.locator('[data-editor="2026-03"] [data-edit="container"]').first();await first.focus();await first.evaluate(el=>{const d=new DataTransfer();d.setData('text/plain','DEMO-A\t\tShipper A\nDEMO-B\tBoat B\t');el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:d,bubbles:true,cancelable:true}));});assert.equal(await page.locator('[data-editor="2026-03"] [data-edit="container"]').count(),2);assert.equal(await page.locator('[data-editor="2026-03"] [data-edit="carrier"]').first().inputValue(),'');assert.equal(await page.locator('[data-editor="2026-03"] [data-edit="shipper"]').first().inputValue(),'Shipper A');assert.equal(await page.locator('[data-editor="2026-03"] [data-edit="shipper"]').last().inputValue(),'');}));
test('batch save is pending only; receipt form opens inside selected month and never posts',async()=>withPage(async page=>{const before=await page.locator('#all-balance').innerText();await page.locator('#month-2026-03 [data-action="open-editor"]').click();await page.locator('[data-editor="2026-03"] [data-action="add"]').click();const row=page.locator('[data-editor="2026-03"] tbody tr').last();await row.locator('[data-edit="date"]').fill('2026-03-12');await row.locator('[data-edit="container"]').fill('C-NEW');await page.locator('[data-editor="2026-03"] [data-action="save"]').click();assert.equal(await page.locator('#all-balance').innerText(),before);await page.locator('#month-2026-03 [data-action="open-receipt"]').click();assert.equal(await page.locator('#receipt-period').inputValue(),'THÁNG 03/2026');await page.locator('#receipt-amount').fill('1000000');await page.locator('#receipt-form button[type="submit"]').click();assert.equal(await page.locator('#all-balance').innerText(),before);assert.match(await page.locator('#receipt-result').innerText(),/Chờ duyệt/);}));
test('scrollable table regions in open month have tabindex, region role, and distinct aria-labels',async()=>withPage(async page=>{
  const items=await page.locator('.month[open] .table-scroll').evaluateAll(els=>els.map(el=>({tabindex:el.getAttribute('tabindex'),role:el.getAttribute('role'),label:el.getAttribute('aria-label')})));
  assert.equal(items.length,3);
  for(const item of items){assert.equal(item.tabindex,'0');assert.equal(item.role,'region');assert.ok(item.label?.trim());}
  assert.equal(new Set(items.map(i=>i.label)).size,3);
}));
