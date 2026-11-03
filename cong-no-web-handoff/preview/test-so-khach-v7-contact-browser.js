/* Trình duyệt (Playwright) cho thẻ Trao đổi và thẻ Hồ sơ của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A3): phiếu thu
 * và cấn trừ đúng ngày, số tiền, tháng trừ nợ theo phân bổ còn hiệu lực, phiếu hủy gạch có lý do; lần nhắc, hội thoại Zalo tìm theo
 * tên, lọc; Copy tin nhắc ghi một dòng "đã nhắc" mỗi ngày; Hồ sơ theo HO-SO-01: giá đang áp bằng dòng "Đang dùng" của Bảng giá,
 * giá sắp áp, chưa có giá, cột phụ phí bằng cột của sổ, group Zalo đã gắn, nút chưa có backend báo rõ; nguồn phụ lỗi thì chỉ khối đó báo. Máy chủ giả, dữ liệu giả, 1280×720, đồng hồ trang ghim
 * 15/11/2026 (giờ VN); không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const TODAY = '2026-11-15';
const M = millions => String(millions * 1000000);
const CHAT = 'a'.repeat(64);
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
const line = (id, month, amount, superseded = null, kind = 'debt') => ({ id, month: `${month}-01`, kind, amount_vnd: M(amount), superseded_by_event: superseded });
const receipt = (id, date, amount, allocations, extra = {}) => ({ id, pid: `PH-00${id}`, date, method: 'THU TIỀN', amount_vnd: M(amount), reference: null,
  voided_by_event: null, void_reason: null, allocations, ...extra });
const DEBT_ROW = { customer_id: 1, name: 'Khách Thử Sửa', outstanding_vnd: M(241), overdue_vnd: M(148), tiers_vnd: [M(43), M(50), M(140), M(8), '0'],
  months: [{ month: '2026-07-01', outstanding_vnd: M(8) }, { month: '2026-08-01', outstanding_vnd: M(140) }, { month: '2026-10-01', outstanding_vnd: M(50) },
    { month: '2026-11-01', outstanding_vnd: M(43) }], risk: 'high' };
const RULE = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };

// Sổ giả: phiếu hủy, cấn trừ từ sổ khác, phiếu có dòng phân bổ đã bị thay (phân bổ lại), phiếu có phần ứng trước, cấn trừ sang sổ khác.
function talking(world) {
  Object.assign(world, { clock: `${TODAY}T10:00:00+07:00`, todayMonth: '2026-11-01', month: null, query: '&the=trao-doi', total: M(241) });
  world.receipts.push(receipt(1, '2026-10-12', 50, [line(1, '2026-09', 50, 90)], { voided_by_event: 90, void_reason: 'Ghi nhầm số tiền', voided_on: '2026-10-13' }),
    receipt(2, '2026-10-20', 157, [line(2, '2026-10', 157)], { method: 'CẤN TRỪ', offset_pair_id: 5, counterparty_customer_id: 2, counterparty_name: 'Sổ Bên Kia' }),
    receipt(3, '2026-11-05', 30, [line(3, '2026-10', 30, 91), line(4, '2026-07', 8), line(5, '2026-08', 22)], { reference: 'CK ngân hàng thử' }),
    receipt(4, '2026-11-10', 12, [line(6, '2026-11', 10), line(7, '2026-11', 2, null, 'advance')]));
  world.outgoing = [{ offset_pair_id: 7, pid: 'PH-009', date: '2026-09-28', method: 'CẤN TRỪ', amount_vnd: '-5000000', void_reason: null, voided_by_event: null,
    counterparty_customer_id: 3, counterparty_name: 'Sổ Khác' }];
  world.reminders = [{ customer_id: 1, last_reminded: '2026-11-10', reminder_count: 3, last_source: 'copy-button' }];
  world.chats = [{ conversation_id: CHAT, display_name: 'Khách Thử Sửa', message_count: 120, last_message_at: Date.parse('2026-11-12T09:30:00+07:00'),
    last_own_message_at: Date.parse('2026-11-11T08:00:00+07:00'), participant_count: 2 },
  { conversation_id: 'b'.repeat(64), display_name: 'Nhóm giả khác', message_count: 5, last_message_at: Date.parse('2026-11-14T09:00:00+07:00') }];
  world.debt = { as_of: TODAY, month: '2026-11-01', rule: RULE, receivable_vnd: M(241), customers: [DEBT_ROW] };
}
// Hồ sơ: sổ sầu riêng cảng, hai cột phụ phí riêng, bảng giá ba đợt (hết hạn, đang dùng, sắp áp dụng), một phiếu có ảnh (ảnh chỉ ở thẻ Sổ).
function profiled(world) {
  talking(world);
  Object.assign(world, { query: '&the=ho-so', feeColumns: [1, 2],
    customers: [{ id: 1, name: 'Khách Thử Sửa', commodity: 'Sầu riêng', transport_mode: 'CANG', status: 'active' }] });
  const rates = (khach, tt) => [{ location: 'LONG AN', tier: 'khach', unit_price_vnd: M(khach) }, { location: 'LONG AN', tier: 'tt', unit_price_vnd: M(tt) },
    { location: 'TIEN GIANG', tier: 'khach', unit_price_vnd: M(khach + 2) }];
  world.priceTable = { tt_shippers: ['SHIP TT'], locations: [{ name: 'TIEN GIANG', aliases: [] }, { name: 'LONG AN', aliases: [] }], periods: [
    { valid_from: '2026-09-15', valid_to: '2026-10-09', rates: rates(55, 70) }, { valid_from: '2026-10-10', valid_to: '2026-11-30', rates: rates(58, 66) },
    { valid_from: '2026-12-01', valid_to: null, rates: rates(60, 68) }] };
  world.images.push({ id: 900, pid: 'PH-003', sha256: 'f'.repeat(64), content_type: 'image/png', data: PNG, removed: false });
}

const items = (page, pane = '#the-trao-doi') => page.locator(`${pane} .ct-item`).evaluateAll(nodes => nodes.map(node =>
  [node.querySelector('time')?.innerText, node.querySelector('b')?.innerText, ...[...node.querySelectorAll('.ct-sub')].map(sub => sub.innerText)]));
const state = page => page.evaluate(() => [document.body.dataset.the, location.search]);
const text = async locator => (await locator.innerText()).replace(/\s+/g, ' ');
const layout = (page, pane) => page.evaluate(selector => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  small: [...document.querySelectorAll(`${selector} :is(button,a.ov-go)`)].map(node => [node.textContent, node.getBoundingClientRect()])
    .filter(([, box]) => box.height < 40 || box.width < 40).map(([text, box]) => `${text} ${box.width}×${box.height}`),
  named: [...document.querySelectorAll(`${selector} button[aria-label]`)].filter(node => !node.ariaLabel.startsWith(node.textContent)).map(node => node.textContent),
  font: getComputedStyle(document.querySelector(selector)).fontSize }), pane);

test('Trao đổi: phiếu thu và cấn trừ đúng ngày, số tiền, tháng trừ nợ hiện hành; phiếu hủy gạch có lý do; lần nhắc, Zalo; lọc theo loại', async () => withPage(async ({ page, world, shot }) => {
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Zalo' }).waitFor();
  await shot('trao-doi');
  assert.deepEqual(await items(page), [
    ['12/11/2026', 'Zalo · tin cuối trong “Khách Thử Sửa”', '120 tin · mình nhắn gần nhất 11/11/2026 · Mở hội thoại'],
    ['10/11/2026', 'Nhắc nợ · bấm Copy tin nhắc', 'Lần nhắc gần nhất · đã nhắc 3 lần'],
    ['10/11/2026', 'Thu tiền 12.000.000 đ', 'Trừ nợ T11/2026 10.000.000 đ · ứng trước 2.000.000 đ'],
    ['05/11/2026', 'Thu tiền 30.000.000 đ', 'Trừ nợ T7/2026 8.000.000 đ · T8/2026 22.000.000 đ', 'Tham chiếu: CK ngân hàng thử'],
    ['20/10/2026', 'Cấn trừ từ Sổ Bên Kia 157.000.000 đ', 'Trừ nợ T10/2026'],
    ['12/10/2026', 'Thu tiền 50.000.000 đ', 'Đã hủy ngày 13/10/2026, không tính tiền · Lý do: Ghi nhầm số tiền'],
    ['28/09/2026', 'Cấn trừ sang Sổ Khác −5.000.000 đ']]);
  // Phiếu hủy: số tiền gạch; dòng phân bổ đã bị thay (T10 của PH-003) không hiện; cấn trừ có đường sang sổ bên kia.
  assert.deepEqual(await page.locator('#the-trao-doi .ct-item.voided s').allInnerTexts(), ['50.000.000 đ']);
  assert.equal(await page.locator('#the-trao-doi .ct-item a', { hasText: 'Sổ Bên Kia' }).getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  // Cùng nguồn với thẻ Sổ: phần trừ nợ của PH-003 ở danh sách phiếu tháng 11 ghi đúng các tháng đó.
  assert.equal(await page.locator('#thang-2026-11 tr:has([data-pid="PH-003"]) .receipt-allocation').innerText(), 'Trừ nợ T7/2026 8.000.000 · T8/2026 22.000.000');
  // Hội thoại tìm theo tên Sheet của sổ như nút Chat ở Đòi nợ; hội thoại khác tên không hiện. Mở chat mở trang Chat Zalo lọc theo tên.
  assert.deepEqual(world.chatReads, ['Khách Thử Sửa']);
  const name = encodeURIComponent('Khách Thử Sửa');
  assert.equal(await page.locator('#the-trao-doi .ct-bar a.ov-go').getAttribute('href'), `/zalo-chat.html?q=${name}`);
  assert.equal(await page.locator('#the-trao-doi .ct-item a', { hasText: 'Mở hội thoại' }).getAttribute('href'), `/zalo-chat.html?q=${name}&c=${CHAT}`);
  assert.equal(await page.locator('#the-trao-doi .ct-status').count(), 0);
  assert.deepEqual(await page.locator('#the-trao-doi .ct-chip').allInnerTexts(), ['Tất cả 7', 'Hứa trả 0', 'Nhắc và Zalo 2', 'Thu tiền 5']);
  await page.locator('#the-trao-doi .ct-chip', { hasText: 'Thu tiền' }).click();
  assert.deepEqual(await page.locator('#the-trao-doi .ct-item').evaluateAll(nodes => nodes.map(node => node.dataset.kind)), Array(5).fill('thu'));
  assert.equal(await page.locator('#the-trao-doi .ct-chip[aria-pressed="true"]').innerText(), 'Thu tiền 5');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.go), 'loai:thu', 'tiêu điểm còn ở nút lọc sau khi vẽ lại');
  await page.locator('#the-trao-doi .ct-chip', { hasText: 'Nhắc và Zalo' }).click();
  assert.deepEqual((await items(page)).map(([date, title]) => `${date} ${title}`), ['12/11/2026 Zalo · tin cuối trong “Khách Thử Sửa”', '10/11/2026 Nhắc nợ · bấm Copy tin nhắc']);
  assert.deepEqual(await layout(page, '#the-trao-doi'), { overflow: 0, small: [], named: [], font: '16px' });
  // Thẻ Tình hình, khối 6: tin Zalo gần nhất cùng hội thoại tìm theo tên.
  await page.locator('#tab-tinh-hinh').click();
  await page.locator('#the-tinh-hinh .ov-activity').waitFor();
  assert.deepEqual(world.requests, [], 'thẻ Trao đổi không gửi lệnh nào khi chỉ xem');
}, talking));

// ZALO-GROUP-01: dấu tin Zalo của sổ trong dòng thời gian, ở ngày của tin; trạng thái do máy chủ tính; dấu đã bỏ gạch có lý do;
// "Mở tin" sang đúng tin; Mở chat mở group đã gắn thay vì tìm theo tên.
function marked(world) {
  talking(world);
  const at = text => new Date(`${text}+07:00`).toISOString();
  world.zaloLinks = [{ conversation_id: CHAT, customer_id: 1, customer_name: 'Khách Thử Sửa' }];
  world.marks = [
    { id: 3, customer_id: 1, kind: 'paid_claim', amount_vnd: M(30), on_date: '2026-11-04', conversation_id: CHAT, message_id: 'm77', message_at: at('2026-11-04T16:00:00'),
      message_sender: 'Vũ', message_excerpt: 'Em chuyển 30 triệu rồi nha', status: 'received', receipt_pid: 'PH-003', created_by: 'hao@example.test', created_on: '2026-11-04' },
    { id: 2, customer_id: 1, kind: 'promise', amount_vnd: M(50), on_date: '2026-11-08', conversation_id: CHAT, message_id: 'm70', message_at: at('2026-11-01T09:15:00'),
      message_sender: 'Vũ', message_excerpt: 'Mai em chuyển 50 triệu', status: 'missed', paid_vnd: M(30), created_by: 'hao@example.test', created_on: '2026-11-01' },
    { id: 1, customer_id: 1, kind: 'note', amount_vnd: null, on_date: null, note: 'Xin giãn tới cuối tháng', conversation_id: null, message_id: null, message_at: null,
      status: 'cancelled', cancel_reason: 'ghi nhầm sổ', created_by: 'hao@example.test', created_on: '2026-10-30' }];
}

test('Trao đổi: dấu tin Zalo ở đúng ngày, trạng thái, Mở tin; lọc Hứa trả; Mở chat mở group đã gắn', async () => withPage(async ({ page, world }) => {
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Hứa trả' }).waitFor();
  const rows = (await items(page)).filter(([, title]) => /Hứa trả|báo đã chuyển|Ghi chú/.test(title));
  assert.deepEqual(rows, [
    ['04/11/2026', 'Khách báo đã chuyển 30.000.000 đ · ngày 04/11/2026', '“Em chuyển 30 triệu rồi nha” — Vũ · Mở tin', 'Đánh dấu bởi hao@example.test'],
    ['01/11/2026', 'Hứa trả 50.000.000 đ · hẹn 08/11/2026', '“Mai em chuyển 50 triệu” — Vũ · Mở tin', 'Đánh dấu bởi hao@example.test'],
    ['30/10/2026', 'Ghi chú: Xin giãn tới cuối tháng', 'Đã bỏ dấu · Lý do: ghi nhầm sổ', 'Đánh dấu bởi hao@example.test']]);
  assert.deepEqual(await page.locator('#the-trao-doi .ct-mark').allInnerTexts(), ['đã có phiếu thu · phiếu PH-003', 'lỡ hẹn · đã trả 30.000.000 đ']);
  assert.equal(await page.locator('#the-trao-doi .ct-item a', { hasText: 'Mở tin' }).first().getAttribute('href'), `/zalo-chat.html?c=${CHAT}&m=m77`);
  assert.equal(await page.locator('#the-trao-doi .ct-item.voided', { hasText: 'Ghi chú' }).count(), 1);
  assert.equal(await page.locator('#the-trao-doi .ct-bar a.ov-go').getAttribute('href'), `/zalo-chat.html?c=${CHAT}`);
  assert.match(await page.locator('#the-trao-doi .ct-status').innerText(), /Group Zalo đã gắn: 1/);
  await page.locator('#the-trao-doi .ct-chip', { hasText: 'Hứa trả' }).click();
  assert.deepEqual(await page.locator('#the-trao-doi .ct-item').evaluateAll(nodes => nodes.map(node => node.dataset.kind)), ['hua', 'hua']);
  assert.deepEqual(await layout(page, '#the-trao-doi'), { overflow: 0, small: [], named: [], font: '16px' });
  assert.deepEqual(world.requests, [], 'xem dấu không gửi lệnh nào');
}, marked));

test('Copy tin nhắc: chép đúng tin của Đòi nợ, ghi một dòng "đã nhắc"; bấm lặp trong ngày không thêm dòng', async () => withPage(async ({ page, world }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Nhắc nợ' }).waitFor();
  const copy = page.locator('#the-trao-doi [data-go="copy"]');
  const reread = () => page.waitForResponse(response => response.url().endsWith('/api/v7/reminders') && response.request().method() === 'GET');
  await Promise.all([reread(), copy.click()]);
  const note = page.locator('#the-trao-doi .ct-note');
  await note.filter({ hasText: 'Đã copy tin nhắc' }).waitFor();
  assert.equal(await note.innerText(), 'Đã copy tin nhắc và ghi “đã nhắc” hôm nay. Dán vào Zalo của khách.');
  // Bộ nhớ tạm của Windows đổi xuống dòng thành \r\n khi đọc lại.
  assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n'), 'Kính gửi Khách Thử Sửa,\nTổng công nợ còn lại: 241.000.000 đ\n'
    + 'Trong đó quá hạn: 148.000.000 đ\nChi tiết nợ theo tháng:\n- Tháng 07/2026: 8.000.000 đ\n- Tháng 08/2026: 140.000.000 đ\n'
    + '- Tháng 10/2026: 50.000.000 đ\n- Tháng 11/2026: 43.000.000 đ\nKính nhờ anh/chị sắp xếp thanh toán giúp. Xin cảm ơn!');
  const reminded = page.locator('#the-trao-doi .ct-item', { hasText: 'Nhắc nợ' });
  await reminded.filter({ hasText: 'đã nhắc 4 lần' }).waitFor();
  assert.equal(await reminded.locator('time').innerText(), '15/11/2026');
  // Bấm lần hai cùng ngày: gửi cùng lệnh, server không thêm dòng (reminder_log UNIQUE theo khách, nguồn, ngày), số lần giữ nguyên.
  await Promise.all([reread(), copy.click()]);
  await note.filter({ hasText: 'Đã copy tin nhắc' }).waitFor();
  assert.equal(await reminded.locator('.ct-sub').innerText(), 'Lần nhắc gần nhất · đã nhắc 4 lần');
  assert.deepEqual(posts(world), [['/api/v7/reminders', { customer_id: 1, source: 'copy-button' }], ['/api/v7/reminders', { customer_id: 1, source: 'copy-button' }]]);
  assert.deepEqual(world.reminderLog, [{ customer_id: 1, source: 'copy-button', reminded_at: TODAY }]);
  assert.equal(world.version, 1, 'ghi "đã nhắc" không đổi phiên bản sổ');
}, talking));

test('Hồ sơ (HO-SO-01): đầu hồ sơ, hai cột đúng thứ tự mục; hạn trả; giá đang áp bằng dòng "Đang dùng" của Bảng giá, giá sắp áp; phụ phí bằng cột của sổ; không còn khối ảnh chứng từ', async () => withPage(async ({ page, world, shot }) => {
  const pane = page.locator('#the-ho-so');
  await pane.locator('.hs-prices').waitFor();
  await pane.locator('.hs-term', { hasText: 'Cuối tháng kế tiếp' }).waitFor();
  await shot('ho-so');
  assert.deepEqual([await pane.locator('.hs-initials').innerText(), await pane.locator('.hs-name').innerText(), await pane.locator('.hs-facts').innerText()],
    ['TS', 'Khách Thử Sửa', 'Sầu riêng · Đường cảng']);
  assert.equal(await page.locator('.book-head').innerText().then(head => head.includes('Sầu riêng')), false, 'mặt hàng chỉ ở đầu hồ sơ');
  assert.deepEqual(await pane.locator('.hs-main h3').allInnerTexts(), ['Thông tin doanh nghiệp', 'Thỏa thuận làm việc', 'Giá và phụ phí áp dụng']);
  assert.deepEqual(await pane.locator('.hs-side h3').allInnerTexts(), ['Người liên hệ', 'Ghi chú khi làm việc', 'Tài liệu'], 'chưa gắn group thì không có mục Nhóm trao đổi');
  const terms = await pane.locator('.hs-term').evaluateAll(nodes => nodes.map(node => node.innerText.replace(/\s+/g, ' ').trim()));
  assert.deepEqual(terms, ['Thanh toán Cuối tháng kế tiếp Công nợ tháng 11/2026 đến hạn 31/12/2026 · quy tắc chung mọi khách',
    'Hạn mức công nợ Chưa đặt hạn mức Chưa đặt nghĩa là chưa giới hạn, không phải 0 đ. Đặt hạn mức', 'Hợp đồng Chưa lưu hợp đồng trên web Tải hợp đồng lên']);
  const digits = value => value.replace(/\D/g, '');
  const rows = await pane.locator('.hs-prices tbody tr').evaluateAll(nodes => nodes.map(node => [node.className, ...[...node.cells].map(cell => cell.innerText)]));
  assert.deepEqual(rows, [['now', 'TIEN GIANG', '60.000.000', '–', '10/10/2026 – 30/11/2026'], ['now', 'LONG AN', '58.000.000', '66.000.000', '10/10/2026 – 30/11/2026'],
    ['next', 'TIEN GIANG', '62.000.000', '–', 'giá mới từ 01/12/2026'], ['next', 'LONG AN', '60.000.000', '68.000.000', 'giá mới từ 01/12/2026']]);
  assert.equal(await pane.locator('.hs-hint').innerText(), 'Đơn vị: đồng/chuyến. Giá TT áp cho shipper SHIP TT; shipper khác lấy giá khách.');
  assert.equal(await pane.locator('.hs-fees').innerText(), 'Phụ phí riêng trên sổ: Neo, Điện');
  assert.equal(await pane.locator('.image-clip').count(), 0, 'ảnh chứng từ xem ở phiếu thu thẻ Sổ');
  assert.deepEqual(await layout(page, '#the-ho-so'), { overflow: 0, small: [], named: [], font: '15px' });
  const geometry = await page.evaluate(() => {
    const box = selector => document.querySelector(selector).getBoundingClientRect();
    const fonts = [...document.querySelectorAll('#the-ho-so :is(p,td,th,span,b,button,a)')].filter(node => node.offsetHeight && node.textContent.trim())
      .map(node => parseFloat(getComputedStyle(node).fontSize));
    return { ratio: Math.round(box('.hs-main').width / (box('.hs-main').width + box('.hs-side').width) * 100), side: box('.hs-side').left > box('.hs-main').right,
      smallest: Math.min(...fonts), name: parseFloat(getComputedStyle(document.querySelector('.hs-name')).fontSize) };
  });
  assert.ok(geometry.side && geometry.ratio >= 58 && geometry.ratio <= 66, `hai cột ${geometry.ratio}/${100 - geometry.ratio}`);
  assert.ok(geometry.smallest >= 14, `chữ nhỏ nhất ${geometry.smallest}px`);
  assert.equal(geometry.name, 30, 'tên khách to nhất thẻ');
  // Xem bảng giá: sang thẻ Sổ, khung Bảng giá mở; các dòng "Đang dùng" hôm nay đúng bằng các dòng giá đang áp ở thẻ Hồ sơ.
  await pane.locator('[data-go="mo:bang-gia"]').click();
  assert.deepEqual((await state(page))[0], 'so');
  await page.locator('.price-table-dialog .price-grid-main td.st-now').first().waitFor();
  const now = await page.locator('.price-table-dialog .price-grid-main tbody tr').evaluateAll(nodes => nodes.filter(node => node.querySelector('td.st-now'))
    .map(node => [...node.querySelectorAll('input')].map(input => input.value)));
  assert.deepEqual(now.map(([, , place, khach, tt]) => [place, digits(khach), digits(tt)]),
    rows.filter(([kind]) => kind === 'now').map(([, place, khach, tt]) => [place, digits(khach), digits(tt)]));
  await page.locator('.price-table-dialog .price-table-close').click();
  // Cài đặt phụ phí mở khung có sẵn ở thẻ Sổ; cột phụ phí riêng là các cột ở tiêu đề sổ, trừ Khác.
  const heads = await page.locator('.ledger-head th.fee-h').allInnerTexts();
  assert.deepEqual(heads.filter(head => head !== 'Khác'), ['Neo', 'Điện']);
  await page.locator('#tab-ho-so').click();
  await pane.locator('[data-go="mo:phu-phi"]').click();
  assert.deepEqual((await state(page))[0], 'so');
  await page.locator('.fee-settings:not([hidden])').waitFor();
  assert.deepEqual(world.requests, [], 'xem hồ sơ không gửi lệnh ghi');
}, profiled));

test('Hồ sơ: nơi đi chưa có giá và giá hết hạn ghi cam ở đúng dòng; group Zalo đã gắn có tên, tin cuối, Mở nhóm; nút chưa có backend báo rõ, không gửi lệnh', async () => withPage(async ({ page, world }) => {
  const pane = page.locator('#the-ho-so');
  await pane.locator('.hs-prices').waitFor();
  await pane.locator('h3', { hasText: 'Nhóm trao đổi' }).waitFor();
  const rows = await pane.locator('.hs-prices tbody tr').evaluateAll(nodes => nodes.map(node => [node.className, ...[...node.cells].map(cell => cell.innerText)]));
  assert.deepEqual(rows, [['warn', 'TIEN GIANG', '57.000.000', '–', 'hết hạn 09/10/2026 · chưa có giá mới'],
    ['warn', 'LONG AN', '55.000.000', '70.000.000', 'hết hạn 09/10/2026 · chưa có giá mới'], ['warn', 'BEN LUC', '–', '–', 'chưa có giá']]);
  assert.equal(await pane.locator('.hs-prices tr.warn td:last-child').first().evaluate(cell => getComputedStyle(cell).color), 'rgb(154, 91, 0)');
  assert.equal(await pane.locator('.hs-fees').innerText(), 'Phụ phí riêng trên sổ: chưa chọn, mọi phụ phí vào cột Khác');
  assert.deepEqual(await pane.locator('.hs-side h3').allInnerTexts(), ['Người liên hệ', 'Nhóm trao đổi', 'Ghi chú khi làm việc', 'Tài liệu']);
  assert.equal(await pane.locator('.hs-person').innerText().then(value => value.replace(/\s+/g, ' ').trim()), 'Z Nhóm giả Hàng bộ Zalo · tin cuối 12/11/2026 Mở nhóm');
  assert.equal(await pane.locator('.hs-person a').getAttribute('href'), `/zalo-chat.html?c=${CHAT}`);
  // Sáu nút của mục cần backend: mỗi nút báo đúng việc, có Đóng; không mở khung giả, không gửi lệnh.
  const buttons = await pane.locator('[data-go^="chua:"]').allInnerTexts();
  assert.deepEqual(buttons, ['Chỉnh sửa hồ sơ', 'Đặt hạn mức', 'Tải hợp đồng lên', '+ Thêm', '+ Thêm ghi chú', 'Tải tài liệu lên']);
  for (const [index, what] of ['Chỉnh sửa hồ sơ', 'Đặt hạn mức', 'Tải hợp đồng lên', 'Thêm người liên hệ', 'Thêm ghi chú', 'Tải tài liệu lên'].entries()) {
    await pane.locator('[data-go^="chua:"]').nth(index).click();
    assert.equal(await pane.locator('.hs-toast span').innerText(), `${what}: chưa lưu được trên web — cần thêm chức năng (giai đoạn B).`);
  }
  assert.equal(await pane.locator('.hs-toast').getAttribute('role'), 'status');
  await pane.locator('.hs-toast [data-go="dong"]').click();
  assert.equal(await pane.locator('.hs-toast').count(), 0);
  assert.deepEqual(world.requests, [], 'nút chưa hỗ trợ không gửi lệnh');
  // 1265 (Chrome Windows có thanh cuộn dọc) và màn hẹp: không cuộn ngang.
  for (const width of [1265, 390]) {
    await page.setViewportSize({ width, height: 720 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, `không cuộn ngang ở ${width}px`);
  }
}, world => {
  profiled(world);
  Object.assign(world, { feeColumns: [], zaloLinks: [{ conversation_id: CHAT, customer_id: 1, customer_name: 'Khách Thử Sửa', linked_by: 'nguoi-thu', linked_at: '2026-11-02T03:00:00Z' }] });
  world.chats[0].display_name = 'Nhóm giả Hàng bộ';
  world.priceTable.locations.push({ name: 'BEN LUC', aliases: [] });
  world.priceTable.periods = world.priceTable.periods.slice(0, 1);
}));

test('Nguồn phụ lỗi: lần nhắc, chat, bảng giá lỗi thì chỉ khối đó báo kèm Thử lại; máy chủ chưa có bản xuất chat thì ghi rõ', async () => withPage(async ({ page, world }) => {
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Zalo' }).waitFor();
  await page.route(/\/api\/v7\/reminders$/, route => route.abort(), { times: 1 });
  await page.reload();
  const error = page.locator('#the-trao-doi .ct-status .ct-error');
  await error.waitFor();
  assert.equal(await text(error), 'Không tải được lần nhắc nợ. Kiểm tra mạng rồi bấm Thử lại. Thử lại');
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Zalo' }).waitFor();
  assert.equal(await page.locator('#the-trao-doi .ct-item[data-kind="thu"]').count(), 5, 'phiếu thu vẫn hiện');
  await error.locator('button').click();
  await page.locator('#the-trao-doi .ct-item', { hasText: 'Nhắc nợ' }).waitFor();
  assert.equal(await page.locator('#the-trao-doi .ct-status').count(), 0);
  // Máy chủ chưa có bản xuất chat (như hao): thẻ Trao đổi báo rõ.
  delete world.chats;
  await page.reload();
  const none = page.locator('#the-trao-doi .ct-status', { hasText: 'Chưa có dữ liệu chat' });
  await none.waitFor();
  assert.equal(await none.innerText(), 'Chưa có dữ liệu chat trên máy chủ.');
  assert.equal(await page.locator('#the-trao-doi .ct-error').count(), 0);
  // Bảng giá lỗi: chỉ khối giá báo lỗi, khối khác của thẻ Hồ sơ vẫn hiện; Thử lại thì có bảng.
  await page.locator('#tab-ho-so').click();
  await page.route(/\/api\/v7\/price-table\?/, route => route.abort(), { times: 1 });
  await page.reload();
  const priceError = page.locator('#the-ho-so .ct-error');
  await priceError.waitFor();
  assert.equal(await text(priceError), 'Không tải được bảng giá. Kiểm tra mạng rồi bấm Thử lại. Thử lại');
  assert.equal(await page.locator('#the-ho-so .hs-facts').innerText(), 'Sầu riêng · Đường cảng');
  await priceError.locator('button').click();
  await page.locator('#the-ho-so .hs-prices').waitFor();
  assert.deepEqual(world.requests, [], 'không gửi lệnh nào');
}, world => { profiled(world); world.query = '&the=trao-doi'; }));
