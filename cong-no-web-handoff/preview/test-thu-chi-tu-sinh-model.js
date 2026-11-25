const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const M = require('./thu-chi-tu-sinh-model.js');

// THU-CHI-02 đợt 0: model bản bấm thử "Thu chi tự sinh". Toàn số bịa. Tiền là BigInt (đồng; cent với USD).
const DAY = '2026-11-24';
const tx = (id, accountId, time, dir, amount, counterparty, content, bankRef = null) => ({ id, accountId, time: `${DAY} ${time}`, dir, amount, currency: accountId === 'tk3' ? 'USD' : 'VND', counterparty, content, bankRef });
const fresh = () => M.newSim();
const put = (sim, ...txns) => assert.equal(M.act(sim, 'importTxns', { time: `${DAY} 09:00`, txns }).ok, true);
const txnOf = (sim, id) => sim.state.txns.find(item => item.id === id);
const makeRequest = (sim, extra = {}) => {
  const result = M.act(sim, 'createRequest', { type: 'chi_thuong', amount: 8000000n, payeeId: 'cang-y', attachment: 'hoa-don-gia.png', time: `${DAY} 09:00`, ...extra });
  assert.equal(result.ok, true);
  return result.id;
};
const approve = (sim, id) => assert.equal(M.act(sim, 'approveRequest', { id, role: 'sep', time: `${DAY} 09:30` }).ok, true);
const sumsOf = sim => {
  const d = M.dongTien(sim.state);
  return [d.vnd, d.usd, d.owed, d.today.vao, d.today.ra, d.today.vaoUsd, d.today.raUsd, d.canSep.waiting, d.canSep.unapproved, d.canSep.unknown, d.canSep.total].map(String);
};

// ---- Kịch bản 11 bước: bảng kỳ vọng số trên Dòng tiền, tính tay từ số dư đầu ngày và các giao dịch của kịch bản ----
// Cột: tiền đồng đang có, USD (cent) đang có, đang ứng, vào hôm nay, ra hôm nay, USD vào, USD ra, chờ duyệt, chi chưa duyệt, tiền về chưa rõ, tổng Cần sếp.
const EXPECTED = [
  ['750000000', '2000000', '20000000', '0', '0', '0', '0', 0, 0, 0, 0],       // 0 đầu ngày
  ['942189000', '2000000', '20000000', '201689000', '9500000', '0', '0', 0, 1, 1, 2],   // 1 sao kê sáng
  ['942189000', '2000000', '20000000', '201689000', '9500000', '0', '0', 0, 1, 0, 1],   // 2 gắn khách
  ['942189000', '2000000', '20000000', '201689000', '9500000', '0', '0', 1, 1, 0, 2],   // 3 tạo đề nghị
  ['942189000', '2000000', '20000000', '201689000', '9500000', '0', '0', 0, 1, 0, 1],   // 4 sếp duyệt
  ['934189000', '2000000', '20000000', '201689000', '17500000', '0', '0', 0, 1, 0, 1],  // 5 chuyển và khớp
  ['934189000', '2000000', '20000000', '201689000', '17500000', '0', '0', 0, 1, 0, 1],  // 6 tiền chờ về
  ['1239589000', '2798500', '20000000', '201689000', '17500000', '1998500', '0', 0, 1, 0, 1],   // 7 USD về, bán USD
  ['1119589000', '2798500', '20000000', '201689000', '137500000', '1998500', '0', 0, 1, 0, 1],  // 8 chi hộ ba lệnh
  ['1114089000', '2798500', '20000000', '201689000', '143000000', '1998500', '0', 0, 2, 0, 2], // 9 chi không đề nghị
  ['1084089000', '2798500', '50000000', '201689000', '173000000', '1998500', '0', 0, 2, 0, 2], // 10 ứng tiền mặt
  ['1084089000', '2798500', '50000000', '201689000', '173000000', '1998500', '0', 0, 2, 0, 2], // 11 kiểm quỹ
].map(row => row.map(String));

test('Kịch bản 11 bước: sau mỗi bước, số trên Dòng tiền bằng bảng kỳ vọng', () => {
  const sim = fresh();
  assert.deepEqual(sumsOf(sim), EXPECTED[0]);
  for (let step = 1; step <= 11; step += 1) {
    assert.equal(M.next(sim), true);
    assert.equal(sim.cursor, step);
    assert.deepEqual(sumsOf(sim), EXPECTED[step], `sau bước ${step}`);
  }
  assert.equal(M.next(sim), false);   // hết ngày
});

test('Người bấm tay trước rồi mới Tiếp: ra đúng số như để Tiếp làm thay', () => {
  const sim = fresh();
  M.next(sim); M.next(sim);
  const id = makeRequest(sim, { container: 'MAUU1000101' });   // nhân viên tạo tay ở bước 3
  assert.equal(id, 'DC0456');
  assert.equal(sim.state.requests[0].tag, 'r1');   // nhận nhãn của bước 3
  assert.equal(M.STEPS[2].done(sim.state), true);
  M.next(sim);
  approve(sim, id);   // sếp bấm tay ở bước 4
  assert.equal(M.STEPS[3].done(sim.state), true);
  M.next(sim);
  M.next(sim);
  assert.equal(sim.state.requests[0].status, 'da_khop');
  assert.deepEqual(sumsOf(sim), EXPECTED[5]);
  assert.equal(sim.state.requests.length, 1);
});

test('Trước: lùi một bước, bỏ cả việc bấm tay của bước đang chờ, rồi đi lại ra đúng số', () => {
  const sim = fresh();
  for (let step = 0; step < 5; step += 1) M.next(sim);
  makeRequest(sim, { type: 'chi_ho', walletId: 'tq1', payeeId: 'nha-vuon-1', amount: 1000n });   // bấm tay khi đang chờ bước 6
  assert.equal(M.back(sim), true);
  assert.equal(sim.cursor, 4);
  assert.deepEqual(sumsOf(sim), EXPECTED[4]);
  assert.equal(sim.state.requests.length, 1);
  assert.equal(sim.state.requests[0].status, 'da_duyet');   // bước 5 chưa làm lại: chỉ còn việc của bước 1–4
  M.back(sim); M.back(sim); M.back(sim); M.back(sim);
  assert.equal(sim.cursor, 0);
  assert.deepEqual(sumsOf(sim), EXPECTED[0]);
  assert.equal(M.back(sim), false);
  for (let step = 1; step <= 11; step += 1) M.next(sim);
  assert.deepEqual(sumsOf(sim), EXPECTED[11]);
  M.reset(sim);
  assert.deepEqual(sumsOf(sim), EXPECTED[0]);
});

test('Sao kê sáng: máy ghép đúng sổ, đúng luật; vài khoản vào hộp ngoại lệ theo thứ tự số tiền', () => {
  const sim = fresh();
  M.next(sim);
  const how = id => [txnOf(sim, id).match?.sheet, txnOf(sim, id).match?.rule];
  assert.deepEqual(how('g01'), ['thu', 'R1']);
  assert.deepEqual(how('g02'), ['thu', 'R2']);
  assert.deepEqual(how('g03'), ['thu', 'R3']);
  assert.deepEqual(how('g04'), ['thu', 'R4']);
  assert.deepEqual(how('g05'), ['thu', 'R5']);
  assert.deepEqual(how('g06'), ['thu', 'R5']);
  assert.deepEqual(how('g10'), ['chi', 'R9']);
  assert.deepEqual(how('g11'), ['noi_bo', 'R8']);
  assert.deepEqual(how('g13'), ['rieng', 'R0']);
  assert.deepEqual(M.exceptions(sim.state).map(item => [item.txn.id, item.kind]), [['g07', 'lech'], ['g08', 'chua_ro'], ['g09', 'chi_chua_de_nghi']]);
});

// ---- Luật ghép R1–R9, mỗi luật một ca ----
test('R1: mã đề nghị trong nội dung (chi) và mã thanh toán trên debit note (thu)', () => {
  const sim = fresh();
  const id = makeRequest(sim);
  approve(sim, id);
  put(sim, tx('a1', 'tk1', '10:00', 'out', 8000000n, 'Cảng Y', `${id} PHI NANG HA`), tx('a2', 'tk1', '10:01', 'in', 7000000n, 'Người lạ', 'HTH0002K CUOC'));
  assert.equal(txnOf(sim, 'a1').match.rule, 'R1');
  assert.equal(txnOf(sim, 'a1').match.requestId, id);
  assert.equal(sim.state.requests[0].status, 'da_khop');
  assert.deepEqual([txnOf(sim, 'a2').match.rule, txnOf(sim, 'a2').match.customerId], ['R1', 'kh-b']);
  assert.equal(sim.state.drafts.at(-1).reference, 'a2');   // phiếu thu điền sẵn, reference = mã giao dịch
});

test('R2: mã ngân hàng trùng reference của phiếu thu đã có', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'in', 1n, 'Ai đó', 'CK', 'FT0001'));   // số tiền không cần bằng: mã là bằng chứng
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.receiptId], ['R2', 'PT0101']);
});

test('R3: người chuyển đã biết; USD của công ty chuyển TQ vào ví khách', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk2', '10:00', 'in', 777n, 'Khách C', 'CK'), tx('a2', 'tk3', '10:01', 'in', 500000n, 'Công ty chuyển TQ 1', 'PAYMENT'));
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.customerId], ['R3', 'kh-c']);
  assert.deepEqual([txnOf(sim, 'a2').match.rule, txnOf(sim, 'a2').match.sheet, txnOf(sim, 'a2').match.walletId], ['R3', 'vi', 'tq1']);
  assert.equal(M.walletView(sim.state, 'tq1').pendingUsd, 500000n);   // USD chờ bán, chưa cộng đồng
});

test('R4: số hóa đơn trong nội dung', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'in', 35000000n, 'Ai đó', 'TT HD0101 NGAY 24'));
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.customerId], ['R4', 'kh-c']);
  assert.equal(sim.state.invoices[0].txnId, 'a1');
});

test('R5: cùng số tiền trong cửa sổ ngày (vào theo phiếu, ra theo đề nghị); ngoài cửa sổ không ghép', () => {
  const sim = fresh();
  const id = makeRequest(sim, { amount: 9000000n });
  approve(sim, id);
  put(sim, tx('a1', 'tk1', '10:00', 'in', 40000000n, 'Ai đó', 'CK'), tx('a2', 'tk1', '10:01', 'out', 9000000n, 'Nhà khác', 'CK'));
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.receiptId], ['R5', 'PT0102']);
  assert.equal(txnOf(sim, 'a2').match.rule, 'R5');
  assert.ok(sim.state.flags.some(flag => flag.type === 'khac_nguoi_nhan'));   // đúng số nhưng khác người nhận: ghép mà vẫn cảnh báo
  // Phiếu ghi cách ngày tiền về quá cửa sổ thì không ghép.
  const other = fresh();
  other.state.receipts[1].date = '2026-11-18';
  put(other, tx('b1', 'tk1', '10:00', 'in', 40000000n, 'Ai đó', 'CK'));
  assert.equal(txnOf(other, 'b1').match, null);
  // Cửa sổ như web/v7_cash_chat.py: phiếu từ 3 ngày trước tới 7 ngày sau ngày tiền về.
  assert.deepEqual([M.MATCH_BEFORE_DAYS, M.MATCH_AFTER_DAYS], [3, 7]);
  for (const [date, matched] of [['2026-11-21', true], ['2026-11-20', false], ['2026-12-01', true], ['2026-12-02', false]]) {
    const edge = fresh();
    edge.state.receipts[1].date = date;
    put(edge, tx('c1', 'tk1', '10:00', 'in', 40000000n, 'Ai đó', 'CK'));
    assert.equal(Boolean(txnOf(edge, 'c1').match), matched, date);
  }
});

test('R6: nhiều lệnh ra cho cùng người nhận cộng dồn vào một đề nghị; vượt số còn lại thì không nhận', () => {
  const sim = fresh();
  const id = makeRequest(sim, { amount: 100000000n, type: 'chi_ho', walletId: 'tq1', payeeId: 'nha-vuon-1' });
  approve(sim, id);
  put(sim, tx('a1', 'tk1', '10:00', 'out', 30000000n, 'Nhà vườn 1', 'LAN 1'), tx('a2', 'tk1', '10:01', 'out', 45000000n, 'Nhà vườn 1', 'LAN 2'));
  assert.deepEqual(['a1', 'a2'].map(key => txnOf(sim, key).match.rule), ['R6', 'R6']);
  assert.equal(M.requestView(sim.state, id).statusText, 'Mới chuyển 75.000.000 đ / 100.000.000 đ');
  put(sim, tx('a3', 'tk1', '10:02', 'out', 30000000n, 'Nhà vườn 1', 'LAN 3'));   // 30 triệu > còn 25 triệu
  assert.equal(txnOf(sim, 'a3').match.rule, null);
  assert.equal(sim.state.requests[0].status, 'da_duyet');
  put(sim, tx('a4', 'tk1', '10:03', 'out', 25000000n, 'Nhà vườn 1', 'LAN 4'));
  assert.equal(sim.state.requests[0].status, 'da_khop');
});

test('Ba lệnh ↔ một đề nghị: đủ ba lệnh thì đóng đề nghị, ví trừ đúng tổng; gửi lại cùng mã giao dịch chỉ ghi một lần', () => {
  const sim = fresh();
  M.next(sim); M.next(sim); M.next(sim); M.next(sim); M.next(sim); M.next(sim); M.next(sim);
  const before = M.walletBalance(sim.state, 'tq1');
  M.next(sim);
  const request = sim.state.requests.find(item => item.tag === 'r2');
  assert.deepEqual([request.status, request.txnIds.length, request.paid], ['da_khop', 3, 120000000n]);
  assert.equal(before - M.walletBalance(sim.state, 'tq1'), 120000000n);
  const again = M.act(sim, 'importTxns', { time: `${DAY} 15:30`, txns: [txnOf(sim, 'g41')] });
  assert.deepEqual([again.added, again.duplicate], [0, 1]);
  assert.equal(sim.state.requests.find(item => item.tag === 'r2').paid, 120000000n);
});

test('R7: bằng tổng nhiều phiếu chỉ gợi ý, không tự ghép', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'in', 55000000n, 'Ai đó', 'CK'));   // phiếu 25 + 30 triệu của Khách B
  assert.equal(txnOf(sim, 'a1').match, null);
  const item = M.exceptions(sim.state).find(entry => entry.txn.id === 'a1');
  assert.equal(item.kind, 'goi_y');
  assert.match(item.text, /PT0101 \+ PT0104 của Khách B/);
});

test('R8: cặp nội bộ giữa hai tài khoản, rút quỹ; cặp đổi tiền bán USD', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'out', 20000000n, 'Quỹ tiền mặt', 'RUT QUY'), tx('a2', 'quy', '10:20', 'in', 20000000n, 'Công ty A', 'NHAN QUY'));
  assert.deepEqual([txnOf(sim, 'a1').match.kind, txnOf(sim, 'a2').match.kind], ['chuyen_noi_bo', 'chuyen_noi_bo']);
  put(sim, tx('a3', 'tk3', '11:00', 'out', 100000n, 'Ngân hàng 1', 'BAN USD'), tx('a4', 'tk1', '11:00', 'in', 25450000n, 'Ngân hàng 1', 'BAN USD'));
  assert.deepEqual([txnOf(sim, 'a3').match.kind, txnOf(sim, 'a4').match.kind], ['doi_tien', 'doi_tien']);
  assert.equal(sim.state.exchanges[0].rate, 25450n);
  // Số đồng lệch tỷ giá ngân hàng quá 1‰ thì không phải cặp đổi tiền.
  put(sim, tx('a5', 'tk3', '11:30', 'out', 100000n, 'Ngân hàng 1', 'BAN USD'), tx('a6', 'tk1', '11:30', 'in', 24000000n, 'Ngân hàng 1', 'BAN USD'));
  assert.equal(txnOf(sim, 'a5').match.rule, null);
  // Không cùng số tiền thì không phải chuyển nội bộ.
  put(sim, tx('a7', 'tk1', '12:00', 'out', 5000000n, 'Công ty B', 'CK NOI BO'), tx('a8', 'tk2', '12:00', 'in', 4000000n, 'Công ty A', 'CK NOI BO'));
  assert.equal(txnOf(sim, 'a7').match.rule, null);
});

test('Cặp đổi tiền: bán USD của khách TQ cộng ví theo tỷ giá tính khách, làm tròn xuống, không qua số thực', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk3', '10:00', 'in', 1234567n, 'Công ty chuyển TQ 1', 'PAYMENT'));   // 12.345,67 USD
  assert.equal(M.walletBalance(sim.state, 'tq1'), 150000000n);   // chưa bán: chưa cộng đồng
  put(sim, tx('a2', 'tk3', '11:00', 'out', 1234567n, 'Ngân hàng 1', 'BAN USD'), tx('a3', 'tk1', '11:00', 'in', 314197301n, 'Ngân hàng 1', 'BAN USD'));
  assert.equal(M.usdToVnd(1234567n, 25300n), 312345451n);   // 12.345,67 × 25.300 = 312.345.451,0 đồng
  assert.equal(M.walletBalance(sim.state, 'tq1') - 150000000n, 312345451n);
  assert.equal(M.exchangeNote(sim.state)[0].rateText, '25.449 đ/USD');   // tỷ giá ngầm định của lần bán, làm tròn xuống đồng
});

test('R9: người nhận định kỳ đã được sếp duyệt chung thì không cờ; người nhận thường thì có cờ', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'out', 6000000n, 'Nhà cung cấp định kỳ 1', 'TIEN THUE'), tx('a2', 'tk1', '10:01', 'out', 6000000n, 'Hãng tàu X', 'TIEN CUOC'));
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.category], ['R9', 'Văn phòng']);
  assert.equal(txnOf(sim, 'a2').match.rule, null);
  assert.deepEqual(M.openFlags(sim.state).map(flag => flag.txnId), ['a2']);
});

test('Hai ứng viên cùng số tiền: không đoán, ghi vào ngoại lệ "có hơn một nơi"', () => {
  const sim = fresh();
  sim.state.receipts.push({ id: 'PT0199', customerId: 'kh-a', amount: 40000000n, date: '2026-11-23', reference: null, txnId: null });
  put(sim, tx('a1', 'tk1', '10:00', 'in', 40000000n, 'Ai đó', 'CK'));
  assert.equal(txnOf(sim, 'a1').match, null);
  assert.equal(M.exceptions(sim.state)[0].kind, 'nhieu');
});

// ---- Phí ngân hàng ----
test('Phí ngân hàng: hụt trong ngưỡng thì vẫn khớp và tách thành dòng phí; ngoài ngưỡng là ngoại lệ (đồng và USD)', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'in', 19950000n, 'Ai đó', 'CK'));   // phiếu 20.000.000, hụt đúng 50.000: còn trong ngưỡng
  assert.deepEqual([txnOf(sim, 'a1').match.rule, txnOf(sim, 'a1').match.fee], ['R5', 50000n]);
  put(sim, tx('a2', 'tk2', '10:01', 'in', 29949999n, 'Ai đó', 'CK'));   // phiếu 30.000.000, hụt 50.001: quá ngưỡng một đồng
  assert.equal(txnOf(sim, 'a2').match, null);
  assert.equal(M.exceptions(sim.state)[0].kind, 'lech');
  assert.deepEqual(M.feeRows(sim.state).map(row => row.amountText), ['50.000 đ']);
  // USD: ngưỡng 40 USD; chờ về 8.000 USD, về 7.960 USD thì vẫn khớp, về 7.959 USD thì không.
  const usd = fresh();
  assert.equal(M.act(usd, 'createExpectation', { walletId: 'tq2', amountText: '8.000', time: `${DAY} 11:00` }).ok, true);
  put(usd, tx('b1', 'tk3', '14:00', 'in', 795900n, 'Công ty chuyển TQ 2', 'PAYMENT'));
  assert.equal(txnOf(usd, 'b1').match, null);
  put(usd, tx('b2', 'tk3', '14:01', 'in', 796000n, 'Công ty chuyển TQ 2', 'PAYMENT'));
  assert.equal(txnOf(usd, 'b2').match.fee, 4000n);
  assert.equal(M.expectationRows(usd.state)[0].statusText, 'Về rồi · phí ngân hàng 40,00 USD');
});

test('Phí ngân hàng của khoản đã tách không làm tăng tiền ra và vào hôm nay; chỉ vào bảng "Tháng này"', () => {
  const sim = fresh();
  const before = M.monthByCategory(sim.state).chi.find(item => item.name === 'Phí ngân hàng').amount;
  put(sim, tx('a1', 'tk1', '10:00', 'in', 19989000n, 'Ai đó', 'CK'));
  assert.equal(M.dongTien(sim.state).today.vao, 19989000n);
  assert.equal(M.dongTien(sim.state).today.ra, 0n);
  assert.equal(M.monthByCategory(sim.state).chi.find(item => item.name === 'Phí ngân hàng').amount - before, 11000n);
});

// ---- Ví khách TQ ----
test('Ví âm và hạn mức: ứng vượt số dư có cảnh báo trước khi duyệt; quá hạn mức hoặc quá lâu có chữ cảnh báo', () => {
  const sim = fresh();
  const id = makeRequest(sim, { type: 'ung_tien_mat', walletId: 'tq2', payeeId: 'nguoi-nhan-1', amount: 30000000n, attachment: '' });
  const view = M.requestView(sim.state, id);
  assert.deepEqual([view.wallet.over, view.wallet.overLimit, view.wallet.balanceText, view.wallet.afterText], [true, false, '−20.000.000 đ', '−50.000.000 đ']);
  sim.state.wallets[1].limit = 40000000n;   // hạn mức thấp hơn số sẽ âm
  assert.equal(M.requestView(sim.state, id).wallet.overLimit, true);
  assert.deepEqual(M.walletView(sim.state, 'tq2').alerts, []);   // chưa chi nên chưa quá
  approve(sim, id);
  assert.equal(M.act(sim, 'handOverCash', { id, photo: true, time: `${DAY} 16:20` }).ok, true);
  assert.match(M.walletAlerts(sim.state)[0], /Khách TQ 2: Ví âm quá hạn mức 40\.000\.000 đ/);
  const old = fresh();
  old.state.wallets[1].negSince = '2026-10-01';
  assert.match(M.walletAlerts(old.state)[0], /Ví âm đã 54 ngày, quá 30 ngày/);
  assert.deepEqual(M.walletAlerts(fresh().state), []);
  // Ví dương không có tuổi âm dù ngày bắt đầu cũ.
  assert.equal(M.walletView(old.state, 'tq1').age, 0);
});

test('Sao kê ví: có dòng "còn lại" sau từng lần; USD chờ bán ghi riêng, không cộng', () => {
  const sim = fresh();
  for (let step = 0; step < 8; step += 1) M.next(sim);
  const rows = M.walletStatement(sim.state, 'tq1');
  assert.deepEqual(rows.map(row => row.afterText), ['150.000.000 đ', '453.600.000 đ', '403.600.000 đ', '363.600.000 đ', '333.600.000 đ']);
  const wait = M.walletStatement(sim.state, 'tq2');
  assert.equal(wait[1].label, 'USD về, chờ bán');
  assert.equal(wait[1].deltaText, '—');
  assert.equal(wait[1].afterText, '−20.000.000 đ');
});

// ---- Vai và cờ ----
test('Chỉ vai Sếp gỡ được cờ "chi chưa duyệt"; kế toán, tiền hàng, nhân viên bị từ chối và cờ vẫn mở', () => {
  const sim = fresh();
  M.next(sim);
  const flag = M.openFlags(sim.state).find(item => item.type === 'chi_chua_duyet');
  for (const role of ['ketoan', 'tienhang', 'nhanvien']) {
    const result = M.run(sim.state, 'approveLate', { flagId: flag.id, role, time: `${DAY} 09:00` });
    assert.deepEqual([result.ok, result.error], [false, 'Việc này chỉ sếp làm.']);
  }
  assert.equal(M.dongTien(sim.state).canSep.unapproved, 1);
  assert.equal(M.act(sim, 'approveLate', { flagId: flag.id, role: 'sep', time: `${DAY} 09:05` }).ok, true);
  assert.equal(M.dongTien(sim.state).canSep.unapproved, 0);
  assert.equal(txnOf(sim, flag.txnId).match.rule, 'DUYET_BU');
  assert.equal(M.act(sim, 'approveLate', { flagId: flag.id, role: 'sep', time: `${DAY} 09:06` }).ok, false);   // cờ đã gỡ
  assert.deepEqual([M.run(sim.state, 'approveRequest', { id: 'DC0456', role: 'ketoan' }).ok, M.run(sim.state, 'rejectRequest', { id: 'DC0456', role: 'nhanvien', reason: 'x' }).ok], [false, false]);
});

test('Việc riêng: không vào tổng, không vào vào/ra hôm nay, nội dung bị che; chủ tài khoản thấy đủ', () => {
  const sim = fresh();
  const before = sumsOf(sim);
  put(sim, tx('p1', 'tk4', '10:00', 'in', 777000000n, 'Người lạ', 'TIEN RIENG'), tx('p2', 'tk4', '10:01', 'out', 1000000n, 'Chợ', 'MUA DO'));
  assert.deepEqual(sumsOf(sim), before);
  assert.equal(M.exceptions(sim.state).length, 0);   // không thành ngoại lệ, không thành cờ
  assert.equal(M.openFlags(sim.state).length, 0);
  assert.equal(M.dongTien(sim.state).personal[0].balance, 30000000n + 777000000n - 1000000n);   // số dư vẫn giữ để kiểm liền mạch
  const [row] = M.txnRows(sim.state, { accountId: 'tk4' });
  assert.deepEqual([row.private, row.who, row.content, row.sheet], [true, 'Việc riêng', '', 'Việc riêng']);
  const own = M.txnRows(sim.state, { accountId: 'tk4', owner: true }).find(item => item.id === 'p1');
  assert.deepEqual([own.who, own.content], ['Người lạ', 'TIEN RIENG']);
  assert.equal(M.monthByCategory(sim.state).thu.some(item => item.name === 'Việc riêng'), false);
});

test('Chuyển trước khi duyệt, khác người nhận, chi hai lần, chi vượt đề nghị đều thành cờ', () => {
  const sim = fresh();
  const id = makeRequest(sim);
  put(sim, tx('a1', 'tk1', '10:00', 'out', 8000000n, 'Cảng Y', `${id} PHI`));   // chưa duyệt đã chuyển
  assert.ok(sim.state.flags.some(flag => flag.type === 'chuyen_truoc_duyet'));
  assert.equal(M.dongTien(sim.state).canSep.unapproved, 1);   // tính vào Cần sếp
  const second = makeRequest(sim, { amount: 3000000n });
  approve(sim, second);
  put(sim, tx('a2', 'tk1', '10:01', 'out', 3000000n, 'Người khác', `${second} CK`));
  assert.ok(sim.state.flags.some(flag => flag.type === 'khac_nguoi_nhan'));
  put(sim, tx('a3', 'tk1', '10:02', 'out', 3000000n, 'Cảng Y', `${second} CK LAI`));
  assert.ok(sim.state.flags.some(flag => flag.type === 'chi_hai_lan'));
  const third = makeRequest(sim, { amount: 1000000n });
  approve(sim, third);
  put(sim, tx('a4', 'tk1', '10:03', 'out', 2000000n, 'Cảng Y', `${third} CK`));
  assert.ok(sim.state.flags.some(flag => flag.type === 'khac_so'));
});

// ---- Nhập liệu và thao tác ----
test('Đọc số tiền: số nguyên dương, ngăn nghìn đều; không đoán số lẻ, "tr", "k", âm, số 0', () => {
  assert.equal(M.parseAmount('8.000.000'), 8000000n);
  assert.equal(M.parseAmount('8,000,000'), 8000000n);
  assert.equal(M.parseAmount('8000000'), 8000000n);
  for (const bad of ['', ' ', '0', '-5', '1,5', '12.5', '8tr', '5k', '1e3', '1.00', 'abc', '1.000.0', '10000000000000']) assert.equal(M.parseAmount(bad), null, bad);
  assert.equal(M.parseDollars('8.000'), 800000n);
  assert.equal(M.parseCount('0'), 0n);   // đếm được 0 đồng là một số thật
  assert.equal(M.parseCount(''), null);   // để trống không phải 0
  assert.equal(M.parseCount('1,5'), null);
});

test('Tạo đề nghị: số tiền, người nhận, loại, khách TQ, ảnh được kiểm; lỗi báo theo từng ô', () => {
  const sim = fresh();
  const bad = M.act(sim, 'createRequest', { type: '', amountText: '1,5', payeeId: '', attachment: '', time: `${DAY} 09:00` });
  assert.equal(bad.ok, false);
  assert.deepEqual(Object.keys(bad.errors).sort(), ['amount', 'payee', 'type']);
  assert.match(bad.errors.amount, /số nguyên lớn hơn 0/);
  assert.equal(sim.state.requests.length, 0);
  const noWallet = M.act(sim, 'createRequest', { type: 'chi_ho', amountText: '1.000.000', payeeId: 'nha-vuon-1', attachment: 'x.png', time: `${DAY} 09:00` });
  assert.deepEqual(Object.keys(noWallet.errors), ['wallet']);
  const noPhoto = M.act(sim, 'createRequest', { type: 'chi_thuong', amountText: '1.000.000', payeeId: 'cang-y', attachment: '', time: `${DAY} 09:00` });
  assert.deepEqual(Object.keys(noPhoto.errors), ['attachment']);
  assert.equal(M.act(sim, 'createRequest', { type: 'chi_thuong', amountText: '1.000.000', payeeId: 'cang-y', attachment: 'a.png', time: `${DAY} 09:00` }).ok, true);
  assert.equal(sim.log.length, 1);   // chỉ thao tác thành công vào nhật ký
});

test('Từ chối bắt buộc lý do; duyệt rồi không từ chối lại được; chưa duyệt thì chưa chuyển', () => {
  const sim = fresh();
  const id = makeRequest(sim);
  assert.deepEqual([M.act(sim, 'rejectRequest', { id, reason: '  ', role: 'sep', time: `${DAY} 09:10` }).ok, sim.state.requests[0].status], [false, 'cho_duyet']);
  assert.equal(M.act(sim, 'markTransferred', { id, time: `${DAY} 09:20` }).ok, false);
  assert.equal(M.act(sim, 'rejectRequest', { id, reason: 'Thiếu hóa đơn', role: 'sep', time: `${DAY} 09:30` }).ok, true);
  assert.deepEqual([sim.state.requests[0].status, M.requestView(sim.state, id).reason], ['tu_choi', 'Thiếu hóa đơn']);
  assert.equal(M.act(sim, 'approveRequest', { id, role: 'sep', time: `${DAY} 09:40` }).ok, false);
});

test('Giao tiền mặt bắt buộc ảnh biên bản và quỹ đủ tiền; kiểm quỹ khớp hoặc lệch có cờ; số đếm để trống bị chặn', () => {
  const sim = fresh();
  const id = makeRequest(sim, { type: 'ung_tien_mat', walletId: 'tq2', payeeId: 'nguoi-nhan-1', amount: 90000000n, attachment: '' });
  approve(sim, id);
  assert.equal(M.act(sim, 'handOverCash', { id, photo: false, time: `${DAY} 16:20` }).error, 'Đính kèm ảnh biên bản bàn giao.');
  assert.equal(M.act(sim, 'handOverCash', { id, photo: true, time: `${DAY} 16:20` }).error, 'Quỹ không đủ tiền mặt.');   // quỹ chỉ có 50 triệu
  assert.equal(M.act(sim, 'countCash', { countedText: '', time: `${DAY} 17:30` }).ok, false);
  const match = M.act(sim, 'countCash', { countedText: '50.000.000', time: `${DAY} 17:30` });
  assert.deepEqual([match.ok, match.diff], [true, 0n]);
  assert.equal(M.openFlags(sim.state).length, 0);
  const off = M.act(sim, 'countCash', { countedText: '49.500.000', time: `${DAY} 17:31` });
  assert.equal(off.diff, -500000n);
  assert.deepEqual(M.openFlags(sim.state).map(flag => [flag.type, flag.text]), [['kiem_quy_lech', 'Lệch −500.000 đ']]);
  assert.deepEqual(M.cashView(sim.state).counts.map(item => item.diffText), ['Khớp', 'Lệch −500.000 đ']);
});

test('Gắn khách cho tiền về chưa rõ: tạo phiếu thu điền sẵn (không ghi sổ nợ), nhớ người chuyển thì lần sau tự ghép bằng R3', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk2', '10:00', 'in', 12000000n, 'Bên thứ ba 1', 'THANH TOAN HO'));
  assert.equal(M.exceptions(sim.state)[0].kind, 'chua_ro');
  assert.equal(M.act(sim, 'attachInflow', { txnId: 'a1', customerId: '', time: `${DAY} 09:10` }).ok, false);
  const done = M.act(sim, 'attachInflow', { txnId: 'a1', customerId: 'kh-a', remember: true, time: `${DAY} 09:10` });
  assert.deepEqual([done.ok, done.remembered], [true, true]);
  assert.deepEqual(M.draftRows(sim.state).map(row => [row.customer, row.amountText, row.reference]), [['Khách A', '12.000.000 đ', 'a1']]);
  put(sim, tx('a2', 'tk2', '11:00', 'in', 1000000n, 'Bên thứ ba 1', 'CK'));
  assert.deepEqual([txnOf(sim, 'a2').match.rule, txnOf(sim, 'a2').match.customerId], ['R3', 'kh-a']);
  assert.equal(M.act(sim, 'attachInflow', { txnId: 'a2', customerId: 'kh-b', time: `${DAY} 11:05` }).ok, false);   // đã ghép rồi
});

test('Lời trao đổi trong đề nghị: nội dung rỗng bị chặn, lời hợp lệ có giờ và người nói', () => {
  const sim = fresh();
  const id = makeRequest(sim);
  assert.equal(M.act(sim, 'addComment', { id, text: '   ', time: `${DAY} 09:05` }).ok, false);
  assert.equal(M.act(sim, 'addComment', { id, text: 'Đã gửi ảnh hóa đơn', by: 'Nhân viên 1', time: `${DAY} 09:06` }).ok, true);
  assert.deepEqual(M.requestView(sim.state, id).comments.map(item => [item.clock, item.by, item.text]), [['09:06', 'Nhân viên 1', 'Đã gửi ảnh hóa đơn']]);
});

test('Tiền chờ về: số đô la nguyên dương và khách bắt buộc; về đủ thì báo "Về rồi" và vào ví chờ bán', () => {
  const sim = fresh();
  assert.deepEqual(Object.keys(M.act(sim, 'createExpectation', { walletId: '', amountText: '8,5', time: `${DAY} 11:00` }).errors).sort(), ['amount', 'wallet']);
  assert.equal(M.act(sim, 'createExpectation', { walletId: 'tq2', amountText: '8.000', time: `${DAY} 11:00` }).ok, true);
  assert.equal(M.expectationRows(sim.state)[0].statusText, 'Đang chờ');
  put(sim, tx('a1', 'tk3', '14:00', 'in', 800000n, 'Công ty chuyển TQ 2', 'PAYMENT'));
  assert.equal(M.expectationRows(sim.state)[0].statusText, 'Về rồi');
  assert.equal(M.walletView(sim.state, 'tq2').pendingUsd, 800000n);
  assert.match(M.lastBot(sim.state).text, /Về rồi: 8\.000,00 USD của Khách TQ 2/);
});

// ---- Số nguyên, không số thực ----
test('Tiền luôn là BigInt, số lớn hơn 2^53 không mất đồng nào, file model không dùng số thực', () => {
  const sim = fresh();
  const big = 9007199254740993n;
  put(sim, tx('a1', 'tk1', '10:00', 'in', big, 'Ai đó', 'CK'));
  assert.equal(typeof M.balanceOf(sim.state, 'tk1'), 'bigint');
  assert.equal(M.balanceOf(sim.state, 'tk1'), 500000000n + big);
  assert.equal(M.money(null), '—');   // thiếu số hiện —, không thành 0
  assert.equal(M.money(0n), '0 đ');
  assert.equal(M.usdText(-1234567n), '−12.345,67 USD');
  for (const value of [M.dongTien(sim.state).vnd, M.dongTien(sim.state).usd, M.dongTien(sim.state).owed]) assert.equal(typeof value, 'bigint');
  const source = fs.readFileSync(path.join(__dirname, 'thu-chi-tu-sinh-model.js'), 'utf8');
  assert.doesNotMatch(source, /parseFloat|toFixed|Math\.round|Math\.floor\(.*amount/);
});

test('Dữ liệu bịa: không có tên người thật, container chỉ tiền tố MAUU, không số tài khoản dài', () => {
  const FX = require('./thu-chi-tu-sinh-fixture.js');
  const text = fs.readFileSync(path.join(__dirname, 'thu-chi-tu-sinh-fixture.js'), 'utf8');
  assert.deepEqual([...new Set(text.match(/\b[A-Z]{4}\d{7}\b/g) ?? [])], ['MAUU1000101']);
  assert.doesNotMatch(text, /["'][0-9]{9,}["']/);   // không có chuỗi số dài kiểu số tài khoản
  assert.equal(FX.accounts.filter(item => item.owner === 'personal').length, 1);
  assert.equal(FX.accounts.length, 5);
});

// ---- Lỗi do review độc lập tìm ra (24/11/2026) ----
test('Sếp từ chối ở bước 4, 8, 10 rồi bấm Tiếp: bước chuyển tiền bị bỏ qua, không có tiền ra, không cờ', () => {
  const sim = fresh();
  for (let step = 0; step < 3; step += 1) M.next(sim);
  assert.equal(M.act(sim, 'rejectRequest', { id: 'DC0456', role: 'sep', reason: 'Thiếu hóa đơn', time: `${DAY} 09:10` }).ok, true);
  M.next(sim);   // bước 4: đã xử lý
  assert.match(M.skipReason(sim, M.stepNow(sim)), /Đề nghị DC0456 đã bị từ chối nên không chuyển tiền./);
  const before = sumsOf(sim);
  M.next(sim);   // bước 5: bỏ qua
  assert.deepEqual(sumsOf(sim), before);
  assert.equal(sim.state.requests[0].paid, 0n);
  assert.equal(M.openFlags(sim.state).filter(flag => flag.type === 'chuyen_truoc_duyet').length, 0);
  M.next(sim); M.next(sim);   // 6, 7
  M.next(sim);   // bước 8: tạo, duyệt, chi hộ như thường
  const second = sim.state.requests.find(item => item.tag === 'r2');
  assert.equal(M.act(sim, 'rejectRequest', { id: second.id, role: 'sep', reason: 'x', time: `${DAY} 15:00` }).ok, false);   // đã duyệt rồi: không từ chối lại
  assert.equal(second.status, 'da_khop');
});

test('Chi hộ ra tiền trước khi duyệt: ví chưa trừ; sếp duyệt thì đề nghị đóng, ví trừ một lần, cờ "chuyển trước giờ duyệt" gỡ', () => {
  const sim = fresh();
  const id = makeRequest(sim, { type: 'chi_ho', walletId: 'tq1', payeeId: 'nha-vuon-1', amount: 10000000n });
  put(sim, tx('a1', 'tk1', '10:00', 'out', 10000000n, 'Nhà vườn 1', `${id} CK`));
  assert.equal(M.walletBalance(sim.state, 'tq1'), 150000000n);   // chưa duyệt: chưa trừ ví
  assert.equal(M.dongTien(sim.state).canSep.unapproved, 1);
  approve(sim, id);
  assert.deepEqual([sim.state.requests[0].status, M.walletBalance(sim.state, 'tq1'), M.dongTien(sim.state).canSep.unapproved], ['da_khop', 140000000n, 0]);
  assert.equal(M.approvedWaiting(sim.state).length, 0);   // không còn hiện ở Chờ chuyển
});

test('Cần sếp đếm cả cờ khác: số trên Dòng tiền bằng số thẻ đang hiện (kiểm quỹ lệch, người nhận khác đề nghị)', () => {
  const sim = fresh();
  assert.equal(M.act(sim, 'countCash', { countedText: '49.000.000', time: `${DAY} 17:30` }).ok, true);
  const d = M.dongTien(sim.state);
  assert.deepEqual([d.canSep.flags, d.canSep.total, M.openFlags(sim.state).length], [1, 1, 1]);
  const second = makeRequest(sim, { amount: 3000000n });
  approve(sim, second);
  put(sim, tx('a1', 'tk1', '10:00', 'out', 3000000n, 'Người khác', `${second} CK`));
  assert.equal(M.dongTien(sim.state).canSep.total, M.openFlags(sim.state).length);
});

test('Cặp nội bộ khớp muộn (chân kia về ở lần nhập sau) gỡ cờ "chi chưa duyệt" của chân đến trước', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk1', '10:00', 'out', 7000000n, 'Công ty B', 'CK NOI BO'));
  assert.equal(M.dongTien(sim.state).canSep.unapproved, 1);
  put(sim, tx('a2', 'tk2', '10:05', 'in', 7000000n, 'Công ty A', 'CK NOI BO'));
  assert.deepEqual([txnOf(sim, 'a1').match.kind, M.dongTien(sim.state).canSep.unapproved], ['chuyen_noi_bo', 0]);
});

test('Phiếu điền sẵn của giao dịch USD hiện đúng đơn vị; hai đề nghị cùng số tiền thì ghi rõ trong ngoại lệ', () => {
  const sim = fresh();
  put(sim, tx('a1', 'tk3', '10:00', 'in', 800000n, 'Ai đó', 'HTH0001K'));
  assert.equal(M.draftRows(sim.state)[0].amountText, '8.000,00 USD');
  const dup = fresh();
  for (const name of ['a', 'b']) { const id = makeRequest(dup, { amount: 5000000n, payeeId: name === 'a' ? 'cang-y' : 'hang-tau-x' }); approve(dup, id); }
  put(dup, tx('b1', 'tk1', '10:00', 'out', 5000000n, 'Người khác', 'CK'));
  assert.match(M.exceptions(dup.state)[0].text, /Có 2 đề nghị cùng số tiền: kế toán chọn./);
});

test('Thao tác chỉ của sếp: thiếu vai cũng bị từ chối (không mở khi quên truyền role)', () => {
  const sim = fresh();
  const id = makeRequest(sim);
  assert.deepEqual([M.run(sim.state, 'approveRequest', { id }).ok, sim.state.requests[0].status], [false, 'cho_duyet']);
});
