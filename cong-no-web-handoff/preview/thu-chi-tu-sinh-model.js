/* THU-CHI-02 đợt 0: phép tính của bản bấm thử "Thu chi tự sinh". Hàm thuần trên một `state` trong bộ nhớ; không gọi API, không đọc
   dữ liệu thật. Mọi phép tính tiền nằm ở file này (ARCH-03), tiền là BigInt ở đơn vị nhỏ nhất (đồng; cent với USD), không số thực.
   Gồm: luật ghép R1–R9, số dư tài khoản và ví khách TQ, đề nghị chi (duyệt, chuyển, khớp), cảnh báo, Dòng tiền, và kịch bản một ngày
   (11 bước) chạy bằng nhật ký thao tác để lùi một bước được. Giao diện (thu-chi-tu-sinh-ui.js) chỉ vẽ chuỗi do file này trả về. */
const ThuChiTuSinhModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const FX = typeof ThuChiTuSinhFixture !== 'undefined' ? ThuChiTuSinhFixture : require('./thu-chi-tu-sinh-fixture.js');

  const ROLES = [
    { id: 'sep', label: 'Sếp', note: 'Duyệt chi, xem dòng tiền' },
    { id: 'ketoan', label: 'Kế toán', note: 'Sổ tiền, ngoại lệ, chuyển tiền, quỹ' },
    { id: 'tienhang', label: 'Tiền hàng', note: 'Ví khách Trung Quốc' },
    { id: 'nhanvien', label: 'Nhân viên', note: 'Đề nghị chi' },
  ];
  // Cửa sổ ngày để ghép theo số tiền (R5): phiếu ghi trước hoặc sau ngày tiền về tối đa chừng này ngày (cùng ý với MATCH_BEFORE/MATCH_AFTER của cash chat).
  const MATCH_BEFORE_DAYS = 3;
  const MATCH_AFTER_DAYS = 3;
  // Ngưỡng phí ngân hàng theo tiền tệ: số về hụt trong ngưỡng thì vẫn khớp, phần hụt là dòng phí (50.000 đồng; 40 USD).
  const FEE_LIMIT = { VND: 50000n, USD: 4000n };
  const WALLET_AGE_DAYS = 30;
  const MAX_AMOUNT = 10n ** 12n;
  const SHEETS = { thu: 'Thu cước', vi: 'Ví khách TQ', chi: 'Chi có duyệt', noi_bo: 'Nội bộ', rieng: 'Việc riêng' };
  const TYPES = { chi_thuong: 'Chi thường', chi_ho: 'Chi hộ khách TQ', ung_tien_mat: 'Ứng tiền mặt' };
  const STATUS_TEXT = { cho_duyet: 'Chờ sếp duyệt', da_duyet: 'Đã duyệt, chờ chuyển', da_chuyen: 'Đã chuyển, chờ ngân hàng', da_khop: 'Đã khớp ngân hàng', tu_choi: 'Bị từ chối' };
  const RULE_TEXT = { R1: 'R1 mã trong nội dung', R2: 'R2 mã ngân hàng của phiếu', R3: 'R3 người chuyển đã biết', R4: 'R4 số hóa đơn', R5: 'R5 cùng số tiền',
    R6: 'R6 nhiều lệnh một đề nghị', R7: 'R7 tổng nhiều phiếu', R8: 'R8 cặp nội bộ', R9: 'R9 người nhận định kỳ', TAY: 'Người làm tay', DUYET_BU: 'Sếp duyệt bù' };
  const RULES_ORDER = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8', 'R9'];
  // Việc nào chỉ vai nào làm: chỉ liệt kê việc có hạn chế; việc không liệt kê thì mọi vai làm được.
  const ONLY = { approveRequest: ['sep'], rejectRequest: ['sep'], approveLate: ['sep'] };
  const UNAPPROVED_FLAGS = ['chi_chua_duyet', 'chuyen_truoc_duyet'];

  // ---- Tiền: định dạng và đọc số ----
  const abs = value => (value < 0n ? -value : value);
  const cmpDesc = (a, b) => (a > b ? -1 : a < b ? 1 : 0);
  const usdText = cents => `${cents < 0n ? '−' : ''}${(abs(cents) / 100n).toLocaleString('vi-VN')},${String(abs(cents) % 100n).padStart(2, '0')} USD`;
  const money = (amount, currency = 'VND') => (amount == null ? '—' : currency === 'USD' ? usdText(amount) : F.full(amount));
  const signedMoney = (amount, currency, dir) => `${dir === 'out' ? '−' : '+'}${money(amount, currency)}`;

  /** Số tiền người gõ: số nguyên dương, chấm hoặc phẩy ngăn nghìn đều; không đoán "1,5", "tr", "k". Trả BigInt hoặc null. */
  function parseAmount(text) {
    const digits = F.readVnd(text, { space: true });
    if (digits === null || !/^[1-9][0-9]*$/.test(digits) || digits.length > 13) return null;
    const value = BigInt(digits);
    return value <= MAX_AMOUNT ? value : null;
  }
  /** Số đô la nguyên người gõ → cent. */
  const parseDollars = text => { const dollars = parseAmount(text); return dollars === null ? null : dollars * 100n; };
  /** Số đếm quỹ: số nguyên không âm; để trống không phải 0. */
  function parseCount(text) {
    const digits = F.readVnd(text, { space: true });
    return digits === null || digits.length > 13 ? null : BigInt(digits);
  }
  /** Số đồng ví của một khoản USD theo tỷ giá nguyên (đồng/USD), làm tròn xuống. */
  const usdToVnd = (cents, rate) => (cents * rate) / 100n;

  // ---- Ngày giờ (chuỗi ISO "2026-11-24 08:05"; không dùng đồng hồ máy) ----
  const dayOf = time => String(time).slice(0, 10);
  const dayNumber = iso => Math.floor(Date.UTC(...iso.split('-').map((part, index) => (index === 1 ? Number(part) - 1 : Number(part)))) / 86400000);
  const daysBetween = (from, to) => dayNumber(dayOf(to)) - dayNumber(dayOf(from));
  const clock = time => String(time).slice(11, 16);
  const inWindow = (receiptDate, txnTime) => {
    const gap = daysBetween(receiptDate, txnTime);   // dương: tiền về sau ngày phiếu
    return gap <= MATCH_BEFORE_DAYS && gap >= -MATCH_AFTER_DAYS;
  };

  // ---- Trạng thái ban đầu ----
  function baseState() {
    const state = {
      today: FX.TODAY, clock: `${FX.TODAY} 08:00`,
      accounts: FX.accounts.map(account => ({ ...account })),
      customers: FX.customers.map(customer => ({ ...customer })),
      wallets: FX.wallets.map(wallet => ({ ...wallet, lines: [] })),
      payees: FX.payees.map(payee => ({ ...payee })),
      payers: Object.fromEntries(Object.entries(FX.payers).map(([name, target]) => [name, { ...target }])),
      receipts: FX.receipts.map(receipt => ({ ...receipt, txnId: null })),
      invoices: FX.invoices.map(invoice => ({ ...invoice, txnId: null })),
      rates: { ...FX.rates },
      txns: [], requests: [], expectations: [], drafts: [], fees: [], exchanges: [], flags: [], counts: [], bot: [], learned: [],
      seq: { code: 456, flag: 1, draft: 1, line: 1, expect: 1 },
    };
    return state;
  }

  const account = (state, id) => state.accounts.find(item => item.id === id);
  const txnById = (state, id) => state.txns.find(item => item.id === id);
  const requestById = (state, id) => state.requests.find(item => item.id === id);
  const payeeById = (state, id) => state.payees.find(item => item.id === id);
  const walletById = (state, id) => state.wallets.find(item => item.id === id);
  const customerById = (state, id) => state.customers.find(item => item.id === id);
  const isPrivate = (state, txn) => account(state, txn.accountId).owner === 'personal';
  const touch = (state, time) => { if (time && time > state.clock) state.clock = time; };
  const say = (state, time, to, text) => state.bot.push({ time, to, text });
  const ok = (extra = {}) => ({ ok: true, ...extra });
  const fail = (error, extra = {}) => ({ ok: false, error, ...extra });
  const allowed = (op, role) => !ONLY[op] || !role || ONLY[op].includes(role);

  // ---- Số dư ----
  const balanceOf = (state, accountId) => {
    let balance = account(state, accountId).opening;
    for (const txn of state.txns) if (txn.accountId === accountId) balance += txn.dir === 'in' ? txn.amount : -txn.amount;
    return balance;
  };
  /** Số dư ví khách TQ bằng đồng: đầu ngày + USD đã đổi theo tỷ giá tính khách − chi hộ − ứng. Âm là công ty đang ứng. */
  function walletBalance(state, walletId) {
    const wallet = walletById(state, walletId);
    let balance = wallet.opening;
    for (const line of wallet.lines) {
      if (line.type === 'vao' && line.converted) balance += line.vnd;
      else if (line.type === 'chi_ho' || line.type === 'ung') balance -= line.vnd;
    }
    return balance;
  }
  const walletPendingUsd = (state, walletId) => walletById(state, walletId).lines.filter(line => line.type === 'vao' && !line.converted)
    .reduce((sum, line) => sum + line.usd, 0n);
  /** Kiểm trước khi duyệt chi hộ hoặc ứng: số dư ví, sau khi chi còn bao nhiêu, có vượt số dư và có quá hạn mức không. */
  function walletCheck(state, request) {
    if (!request.walletId) return null;
    const wallet = walletById(state, request.walletId);
    const balance = walletBalance(state, request.walletId);
    const after = balance - request.amount;
    return { walletId: wallet.id, name: wallet.name, balance, after, over: request.amount > (balance > 0n ? balance : 0n), overLimit: after < -wallet.limit, limit: wallet.limit };
  }

  // ---- Tìm ứng viên ghép: mỗi luật trả danh sách; chỉ nhận khi có đúng một ----
  const codesIn = (content, pattern) => [...new Set(String(content).match(pattern) ?? [])];
  const remaining = request => request.amount - request.paid;
  const unresolved = txn => !txn.match || txn.match.rule === null;

  function ruleR1(state, txn) {
    if (txn.dir === 'in') {
      return state.customers.filter(customer => codesIn(txn.content, /\bHTH\d{4}K\b/g).includes(customer.code))
        .map(customer => ({ rule: 'R1', sheet: 'thu', customerId: customer.id }));
    }
    return state.requests.filter(request => codesIn(txn.content, /\bDC\d{4}\b/g).includes(request.code))
      .map(request => ({ rule: 'R1', sheet: request.type === 'chi_thuong' ? 'chi' : 'vi', requestId: request.id }));
  }
  const ruleR2 = (state, txn) => (txn.dir !== 'in' || !txn.bankRef ? [] : state.receipts.filter(receipt => receipt.reference === txn.bankRef && !receipt.txnId)
    .map(receipt => ({ rule: 'R2', sheet: 'thu', customerId: receipt.customerId, receiptId: receipt.id })));
  function ruleR3(state, txn) {
    const target = txn.dir === 'in' ? state.payers[txn.counterparty] : null;
    return target ? [{ rule: 'R3', ...target }] : [];
  }
  const ruleR4 = (state, txn) => (txn.dir !== 'in' ? [] : state.invoices.filter(invoice => !invoice.txnId && codesIn(txn.content, /\bHD\d{4}\b/g).includes(invoice.id))
    .map(invoice => ({ rule: 'R4', sheet: 'thu', customerId: invoice.customerId, invoiceId: invoice.id })));
  /** Ứng viên theo số tiền cho tiền vào: phiếu chưa có tiền và tiền chờ về. `exact` đúng số; không thì cho phép hụt trong ngưỡng phí. */
  function inboundBySum(state, txn, tolerant) {
    const fits = expected => (tolerant ? expected > txn.amount && expected - txn.amount <= FEE_LIMIT[txn.currency] : expected === txn.amount);
    const feeOf = expected => (tolerant ? expected - txn.amount : 0n);
    const found = [];
    if (txn.currency === 'VND') {
      for (const receipt of state.receipts) {
        if (!receipt.txnId && fits(receipt.amount) && inWindow(receipt.date, txn.time)) found.push({ rule: 'R5', sheet: 'thu', customerId: receipt.customerId, receiptId: receipt.id, fee: feeOf(receipt.amount) });
      }
    }
    for (const expect of state.expectations) {
      if (expect.status === 'cho' && expect.currency === txn.currency && expect.accountId === txn.accountId && fits(expect.amount)) {
        found.push({ rule: 'R5', sheet: 'vi', walletId: expect.walletId, expectId: expect.id, fee: feeOf(expect.amount) });
      }
    }
    return found;
  }
  function ruleR5(state, txn) {
    if (txn.dir === 'in') {
      const exact = inboundBySum(state, txn, false);
      return exact.length ? exact : inboundBySum(state, txn, true);
    }
    return state.requests.filter(request => request.status !== 'cho_duyet' && request.status !== 'tu_choi' && request.currency === txn.currency && remaining(request) === txn.amount)
      .map(request => ({ rule: 'R5', sheet: request.type === 'chi_thuong' ? 'chi' : 'vi', requestId: request.id }));
  }
  /** R6: nhiều lệnh ra cho cùng một người nhận cộng dồn vào một đề nghị đã duyệt, miễn không vượt số còn lại. */
  const ruleR6 = (state, txn) => (txn.dir !== 'out' ? [] : state.requests.filter(request => (request.status === 'da_duyet' || request.status === 'da_chuyen')
    && request.currency === txn.currency && payeeById(state, request.payeeId).name === txn.counterparty && txn.amount <= remaining(request))
    .map(request => ({ rule: 'R6', sheet: request.type === 'chi_thuong' ? 'chi' : 'vi', requestId: request.id })));
  function subsetsOf(items, min, max) {
    const out = [];
    const walk = (start, picked) => {
      if (picked.length >= min) out.push(picked);
      if (picked.length === max) return;
      for (let index = start; index < items.length; index += 1) walk(index + 1, [...picked, items[index]]);
    };
    walk(0, []);
    return out;
  }
  /** R7: tiền về bằng tổng 2–4 phiếu chưa có tiền của một khách: chỉ gợi ý, không tự ghép. Ghi vào `txn.hint`, không trả ứng viên. */
  function ruleR7(state, txn) {
    if (txn.dir !== 'in' || txn.currency !== 'VND') return [];
    const found = [];
    for (const customer of state.customers) {
      const open = state.receipts.filter(receipt => receipt.customerId === customer.id && !receipt.txnId && inWindow(receipt.date, txn.time));
      for (const group of subsetsOf(open, 2, 4)) if (group.reduce((sum, receipt) => sum + receipt.amount, 0n) === txn.amount) found.push({ customerId: customer.id, receiptIds: group.map(receipt => receipt.id) });
    }
    if (found.length === 1) txn.hint = { kind: 'goi_y', rule: 'R7', ...found[0] };
    return [];
  }
  const isOwn = name => FX.ownNames.includes(name);
  /** R8: cặp nội bộ (chuyển giữa tài khoản, rút quỹ) và cặp đổi tiền (bán USD lấy đồng theo tỷ giá ngân hàng, lệch tối đa 1‰). */
  function ruleR8(state, txn) {
    const others = state.txns.filter(other => other !== txn && unresolved(other) && other.accountId !== txn.accountId && other.dir !== txn.dir);
    const found = [];
    if (/BAN USD/i.test(txn.content)) {
      for (const other of others.filter(item => /BAN USD/i.test(item.content) && dayOf(item.time) === dayOf(txn.time) && item.currency !== txn.currency)) {
        const usd = txn.currency === 'USD' ? txn : other;
        const vnd = txn.currency === 'USD' ? other : txn;
        if (usd.dir !== 'out' || vnd.dir !== 'in') continue;
        const expected = usdToVnd(usd.amount, state.rates.bank);
        if (abs(vnd.amount - expected) * 1000n <= expected) found.push({ rule: 'R8', sheet: 'noi_bo', kind: 'doi_tien', pairId: other.id });
      }
      return found;
    }
    if (!isOwn(txn.counterparty)) return [];
    for (const other of others) {
      if (isOwn(other.counterparty) && other.currency === txn.currency && other.amount === txn.amount && Math.abs(daysBetween(other.time, txn.time)) <= 1) {
        found.push({ rule: 'R8', sheet: 'noi_bo', kind: 'chuyen_noi_bo', pairId: other.id });
      }
    }
    return found;
  }
  const ruleR9 = (state, txn) => (txn.dir !== 'out' ? [] : state.payees.filter(payee => payee.standing && payee.name === txn.counterparty)
    .map(payee => ({ rule: 'R9', sheet: 'chi', payeeId: payee.id })));
  const RULE_FN = { R1: ruleR1, R2: ruleR2, R3: ruleR3, R4: ruleR4, R5: ruleR5, R6: ruleR6, R7: ruleR7, R8: ruleR8, R9: ruleR9 };

  /** Kết quả tìm cho một giao dịch: { candidate } khi đúng một ứng viên, { ambiguous } khi một luật có hơn một, {} khi không có. Dừng ở luật đầu có ứng viên. */
  function findMatch(state, txn) {
    for (const id of RULES_ORDER) {
      const list = RULE_FN[id](state, txn);
      if (list.length === 1) return { candidate: list[0] };
      if (list.length > 1) return { ambiguous: { rule: id, count: list.length } };
    }
    return {};
  }

  // ---- Áp một ghép ----
  function addFlag(state, type, extra) {
    const flag = { id: `c${state.seq.flag}`, type, open: true, ...extra };
    state.seq.flag += 1;
    state.flags.push(flag);
    return flag;
  }
  function addDraft(state, customerId, txn) {
    const draft = { id: `PD${String(state.seq.draft).padStart(3, '0')}`, customerId, amount: txn.amount, date: dayOf(txn.time), reference: txn.id, txnId: txn.id, status: 'cho_ghi' };
    state.seq.draft += 1;
    state.drafts.push(draft);
    return draft;
  }
  function pushLine(state, walletId, line) {
    const wallet = walletById(state, walletId);
    const full = { id: `l${state.seq.line}`, ...line };
    state.seq.line += 1;
    wallet.lines.push(full);
    return full;
  }
  function attachToRequest(state, txn, request, rule) {
    request.txnIds.push(txn.id);
    request.paid += txn.amount;
    const payee = payeeById(state, request.payeeId);
    const category = request.type === 'chi_thuong' ? payee.category : null;
    txn.match = { sheet: request.type === 'chi_thuong' ? 'chi' : 'vi', rule, requestId: request.id, category };
    if (request.status === 'cho_duyet' || request.status === 'tu_choi') addFlag(state, 'chuyen_truoc_duyet', { txnId: txn.id, requestId: request.id });
    if (request.status === 'da_khop') addFlag(state, 'chi_hai_lan', { txnId: txn.id, requestId: request.id });
    if (txn.counterparty !== payee.name && account(state, txn.accountId).kind !== 'cash') addFlag(state, 'khac_nguoi_nhan', { txnId: txn.id, requestId: request.id });
    if (request.paid > request.amount) addFlag(state, 'khac_so', { txnId: txn.id, requestId: request.id });
    const done = request.paid >= request.amount && (request.status === 'da_duyet' || request.status === 'da_chuyen');
    if (done) request.status = 'da_khop';
    request.events.push({ at: txn.time, what: 'khop', by: 'Ngân hàng', text: done ? `Ra ${money(txn.amount)}: khớp đủ đề nghị` : `Ra ${money(txn.amount)}: mới ${money(request.paid)} / ${money(request.amount)}` });
    if (request.type !== 'chi_thuong') pushLine(state, request.walletId, { type: request.type === 'chi_ho' ? 'chi_ho' : 'ung', time: txn.time, vnd: txn.amount, txnId: txn.id, requestId: request.id });
    if (done) say(state, txn.time, request.by, `${request.code} đã khớp với giao dịch ngân hàng.`);
  }
  function convertWalletLine(state, usdTxn) {
    const lines = state.wallets.flatMap(wallet => wallet.lines.map(line => ({ wallet, line }))).filter(({ line }) => line.type === 'vao' && !line.converted && line.usd === usdTxn.amount);
    if (lines.length !== 1) return;   // không đoán khi có hơn một dòng cùng số
    const { line } = lines[0];
    line.converted = true;
    line.rate = state.rates.customer;
    line.vnd = usdToVnd(line.usd, state.rates.customer);
  }
  function applyMatch(state, txn, cand) {
    txn.hint = null;
    if (cand.kind === 'doi_tien' || cand.kind === 'chuyen_noi_bo') {
      const other = txnById(state, cand.pairId);
      txn.match = { sheet: 'noi_bo', rule: 'R8', kind: cand.kind, pairId: other.id };
      other.match = { sheet: 'noi_bo', rule: 'R8', kind: cand.kind, pairId: txn.id };
      if (cand.kind === 'doi_tien') {
        const usd = txn.currency === 'USD' ? txn : other;
        const vnd = txn.currency === 'USD' ? other : txn;
        state.exchanges.push({ usdTxnId: usd.id, vndTxnId: vnd.id, usd: usd.amount, vnd: vnd.amount, rate: (vnd.amount * 100n) / usd.amount });
        convertWalletLine(state, usd);
      }
      return;
    }
    if (cand.requestId) {
      const request = requestById(state, cand.requestId);
      const flagged = txn.match && txn.match.rule === null;
      attachToRequest(state, txn, request, cand.rule);
      if (flagged) for (const flag of state.flags) if (flag.txnId === txn.id && flag.type === 'chi_chua_duyet') flag.open = false;
      return;
    }
    if (cand.sheet === 'chi') {   // R9: người nhận định kỳ đã được sếp duyệt chung
      const payee = payeeById(state, cand.payeeId);
      txn.match = { sheet: 'chi', rule: 'R9', category: payee.category, standing: true };
      return;
    }
    if (cand.sheet === 'vi') {
      txn.match = { sheet: 'vi', rule: cand.rule, walletId: cand.walletId, expectId: cand.expectId ?? null };
      if (cand.expectId) {
        const expect = state.expectations.find(item => item.id === cand.expectId);
        expect.status = 've';
        expect.txnId = txn.id;
        expect.fee = cand.fee ?? 0n;
        if (expect.fee > 0n) { state.fees.push({ txnId: txn.id, amount: expect.fee, currency: txn.currency, forId: expect.id }); txn.match.fee = expect.fee; }
        say(state, txn.time, 'Người lo tiền hàng', `Về rồi: ${money(txn.amount, txn.currency)} của ${walletById(state, expect.walletId).name}.`);
      }
      if (txn.currency === 'USD') pushLine(state, cand.walletId, { type: 'vao', time: txn.time, usd: txn.amount, converted: false, txnId: txn.id });
      else pushLine(state, cand.walletId, { type: 'vao', time: txn.time, usd: 0n, converted: true, vnd: txn.amount, rate: 1n, txnId: txn.id });
      return;
    }
    // sheet 'thu'
    txn.match = { sheet: 'thu', rule: cand.rule, customerId: cand.customerId };
    if (cand.receiptId) {
      const receipt = state.receipts.find(item => item.id === cand.receiptId);
      receipt.txnId = txn.id;
      txn.match.receiptId = receipt.id;
      if (cand.fee > 0n) { state.fees.push({ txnId: txn.id, amount: cand.fee, currency: txn.currency, forId: receipt.id }); txn.match.fee = cand.fee; }
      return;
    }
    if (cand.invoiceId) state.invoices.find(item => item.id === cand.invoiceId).txnId = txn.id;
    txn.match.draftId = addDraft(state, cand.customerId, txn).id;
  }

  /** Dấu gợi ý cho tiền về chưa ghép được: hụt quá ngưỡng phí so với đúng một phiếu ("lệch do phí"). */
  function nearMiss(state, txn) {
    if (txn.dir !== 'in' || txn.currency !== 'VND') return null;
    const near = state.receipts.filter(receipt => !receipt.txnId && inWindow(receipt.date, txn.time) && receipt.amount > txn.amount
      && receipt.amount - txn.amount > FEE_LIMIT.VND && (receipt.amount - txn.amount) * 20n <= receipt.amount);
    return near.length === 1 ? { kind: 'lech', receiptId: near[0].id, customerId: near[0].customerId, short: near[0].amount - txn.amount } : null;
  }

  /** Chạy mọi luật cho các giao dịch chưa ghép tới khi không còn gì đổi. Giao dịch tài khoản cá nhân là việc riêng: không ghép, không vào thống kê. */
  function autoMatch(state) {
    let changed = true;
    while (changed) {
      changed = false;
      for (const txn of state.txns) {
        if (!unresolved(txn)) continue;
        if (isPrivate(state, txn)) { txn.match = { sheet: 'rieng', rule: 'R0' }; changed = true; continue; }
        const found = findMatch(state, txn);
        if (found.candidate) { applyMatch(state, txn, found.candidate); changed = true; continue; }
        if (found.ambiguous) txn.hint = { kind: 'nhieu', ...found.ambiguous };
        else txn.hint = txn.hint?.kind === 'goi_y' ? txn.hint : nearMiss(state, txn);
        if (txn.dir === 'out' && !txn.match) {   // chi chưa có đề nghị: cờ đỏ chờ sếp duyệt bù
          txn.match = { sheet: 'chi', rule: null, category: 'Chưa có đề nghị' };
          addFlag(state, 'chi_chua_duyet', { txnId: txn.id });
          changed = true;
        }
      }
    }
  }

  // ---- Thao tác (mỗi thao tác trả { ok } hoặc { ok:false, error }) ----
  const OPS = {
    /** Sao kê về: thêm giao dịch mới (trùng mã thì bỏ), rồi máy ghép. */
    importTxns(state, args) {
      let added = 0;
      let duplicate = 0;
      for (const raw of args.txns) {
        if (txnById(state, raw.id)) { duplicate += 1; continue; }
        state.txns.push({ ...raw, match: null, hint: null });
        added += 1;
        touch(state, raw.time);
      }
      touch(state, args.time);
      autoMatch(state);
      return ok({ added, duplicate });
    },
    /** Kế toán gắn một khoản tiền về chưa rõ cho một khách; tùy chọn nhớ người chuyển. Tạo phiếu thu điền sẵn, không ghi sổ nợ. */
    attachInflow(state, args) {
      const txn = txnById(state, args.txnId);
      if (!txn || txn.dir !== 'in' || !unresolved(txn) || isPrivate(state, txn)) return fail('Khoản này không gắn khách được.');
      if (txn.currency !== 'VND') return fail('Chỉ gắn khoản đồng cho khách; tiền USD vào ví khách TQ.');
      if (!customerById(state, args.customerId)) return fail('Chọn khách.');
      txn.match = { sheet: 'thu', rule: 'TAY', customerId: args.customerId, by: args.by ?? 'Kế toán' };
      txn.hint = null;
      txn.match.draftId = addDraft(state, args.customerId, txn).id;
      let remembered = false;
      if (args.remember && txn.counterparty && !state.payers[txn.counterparty]) {
        state.payers[txn.counterparty] = { sheet: 'thu', customerId: args.customerId };
        state.learned.push(txn.counterparty);
        remembered = true;
      }
      touch(state, args.time);
      return ok({ draftId: txn.match.draftId, remembered });
    },
    createRequest(state, args) {
      const errors = {};
      if (!TYPES[args.type]) errors.type = 'Chọn loại chi.';
      const amount = typeof args.amount === 'bigint' ? args.amount : parseAmount(args.amountText);
      if (!(amount > 0n)) errors.amount = 'Nhập số tiền là số nguyên lớn hơn 0, ví dụ 8.000.000.';
      const payee = payeeById(state, args.payeeId);
      if (!payee) errors.payee = 'Chọn người nhận trong danh sách.';
      if ((args.type === 'chi_ho' || args.type === 'ung_tien_mat') && !walletById(state, args.walletId)) errors.wallet = 'Chọn khách Trung Quốc.';
      if ((args.type === 'chi_thuong' || args.type === 'chi_ho') && !String(args.attachment ?? '').trim()) errors.attachment = 'Đính kèm ảnh hóa đơn hoặc bảng kê.';
      if (Object.keys(errors).length) return fail('Còn ô chưa đúng.', { errors });
      const code = `DC${String(state.seq.code).padStart(4, '0')}`;
      state.seq.code += 1;
      const request = { id: code, code, tag: args.tag ?? null, type: args.type, amount, currency: 'VND', payeeId: payee.id, walletId: args.walletId ?? null,
        container: String(args.container ?? '').trim(), note: String(args.note ?? '').trim(), attachment: args.attachment ?? '', by: args.by ?? 'Nhân viên 1',
        status: 'cho_duyet', paid: 0n, txnIds: [], comments: [], events: [{ at: args.time, what: 'tao', by: args.by ?? 'Nhân viên 1', text: 'Tạo đề nghị' }] };
      state.requests.push(request);
      touch(state, args.time);
      say(state, args.time, 'Sếp', `Có đề nghị ${code} chờ duyệt.`);
      return ok({ id: request.id, code });
    },
    approveRequest(state, args) {
      const request = requestById(state, args.id);
      if (!request) return fail('Không thấy đề nghị.');
      if (request.status !== 'cho_duyet') return fail('Đề nghị này không còn chờ duyệt.');
      request.status = 'da_duyet';
      const check = walletCheck(state, request);
      request.events.push({ at: args.time, what: 'duyet', by: 'Sếp', text: check?.over ? `Duyệt, vượt số dư ví: ví ${money(check.balance)}, đề nghị ${money(request.amount)}` : 'Duyệt' });
      touch(state, args.time);
      say(state, args.time, request.by, `${request.code} đã được duyệt.`);
      // Giao dịch ra trước khi duyệt (cờ "chuyển trước giờ duyệt") vẫn là cờ; không tự gỡ.
      return ok();
    },
    rejectRequest(state, args) {
      const request = requestById(state, args.id);
      if (!request) return fail('Không thấy đề nghị.');
      if (!String(args.reason ?? '').trim()) return fail('Ghi lý do từ chối.', { errors: { reason: 'Ghi lý do từ chối.' } });
      if (request.status !== 'cho_duyet') return fail('Đề nghị này không còn chờ duyệt.');
      request.status = 'tu_choi';
      request.reason = String(args.reason).trim();
      request.events.push({ at: args.time, what: 'tu_choi', by: 'Sếp', text: `Từ chối: ${request.reason}` });
      touch(state, args.time);
      say(state, args.time, request.by, `${request.code} bị từ chối: ${request.reason}.`);
      return ok();
    },
    /** Kế toán đã chuyển tiền (mô phỏng, không có lệnh thật). Chỉ chuyển được đề nghị đã duyệt. */
    markTransferred(state, args) {
      const request = requestById(state, args.id);
      if (!request) return fail('Không thấy đề nghị.');
      if (request.status !== 'da_duyet') return fail('Chưa được duyệt thì chưa chuyển.');
      request.status = 'da_chuyen';
      request.events.push({ at: args.time, what: 'chuyen', by: 'Kế toán', text: 'Đã chuyển (mô phỏng)' });
      touch(state, args.time);
      return ok();
    },
    /** Duyệt bù: chỉ sếp gỡ cờ chi chưa duyệt. Người chuyển tiền hay người phân loại không tự gỡ. */
    approveLate(state, args) {
      const flag = state.flags.find(item => item.id === args.flagId);
      if (!flag || !flag.open || !UNAPPROVED_FLAGS.includes(flag.type)) return fail('Không có cờ để duyệt bù.');
      flag.open = false;
      flag.by = 'Sếp';
      flag.at = args.time;
      const txn = txnById(state, flag.txnId);
      if (txn?.match && txn.match.rule === null) txn.match.rule = 'DUYET_BU';
      touch(state, args.time);
      return ok();
    },
    /** Thủ quỹ giao tiền mặt cho một đề nghị ứng đã duyệt: bắt buộc có ảnh biên bản bàn giao; quỹ phải đủ tiền. */
    handOverCash(state, args) {
      const request = requestById(state, args.id);
      if (!request || request.type !== 'ung_tien_mat') return fail('Không phải đề nghị ứng tiền mặt.');
      if (request.status !== 'da_duyet') return fail('Chưa được duyệt thì chưa giao tiền.');
      if (!args.photo) return fail('Đính kèm ảnh biên bản bàn giao.', { errors: { photo: 'Đính kèm ảnh biên bản bàn giao.' } });
      const amount = remaining(request);
      if (balanceOf(state, 'quy') < amount) return fail('Quỹ không đủ tiền mặt.');
      request.handover = { photo: true, time: args.time };
      request.events.push({ at: args.time, what: 'chuyen', by: 'Thủ quỹ', text: 'Giao tiền mặt, có ảnh biên bản (ảnh giả)' });
      const payee = payeeById(state, request.payeeId);
      return OPS.importTxns(state, { time: args.time, txns: [{ id: `cash-${request.code}`, accountId: 'quy', time: args.time, dir: 'out', amount, currency: 'VND',
        counterparty: payee.name, content: `GIAO TIEN MAT ${request.code}`, bankRef: null }] });
    },
    createExpectation(state, args) {
      const errors = {};
      const wallet = walletById(state, args.walletId);
      if (!wallet) errors.wallet = 'Chọn khách Trung Quốc.';
      const amount = typeof args.amount === 'bigint' ? args.amount : parseDollars(args.amountText);
      if (!(amount > 0n)) errors.amount = 'Nhập số đô la nguyên lớn hơn 0, ví dụ 8.000.';
      if (Object.keys(errors).length) return fail('Còn ô chưa đúng.', { errors });
      const expect = { id: `e${state.seq.expect}`, walletId: wallet.id, amount, currency: 'USD', accountId: 'tk3', note: String(args.note ?? '').trim(), status: 'cho', createdAt: args.time };
      state.seq.expect += 1;
      state.expectations.push(expect);
      touch(state, args.time);
      return ok({ id: expect.id });
    },
    countCash(state, args) {
      const counted = typeof args.counted === 'bigint' ? args.counted : parseCount(args.countedText);
      if (counted === null) return fail('Nhập số tiền đếm được (số nguyên, không âm).', { errors: { counted: 'Nhập số tiền đếm được (số nguyên, không âm).' } });
      const expected = balanceOf(state, 'quy');
      const entry = { time: args.time, counted, expected, diff: counted - expected };
      state.counts.push(entry);
      if (entry.diff !== 0n) addFlag(state, 'kiem_quy_lech', { diff: entry.diff });
      touch(state, args.time);
      return ok({ diff: entry.diff });
    },
    addComment(state, args) {
      const request = requestById(state, args.id);
      const text = String(args.text ?? '').trim();
      if (!request) return fail('Không thấy đề nghị.');
      if (!text) return fail('Gõ nội dung trao đổi.', { errors: { text: 'Gõ nội dung trao đổi.' } });
      request.comments.push({ at: args.time, by: args.by ?? 'Nhân viên 1', text });
      touch(state, args.time);
      return ok();
    },
  };

  /** Chạy một thao tác trên state; từ chối thao tác ngoài vai. */
  function run(state, op, args) {
    if (!OPS[op]) return fail('Thao tác không có.');
    if (!allowed(op, args.role)) return fail('Việc này chỉ sếp làm.');
    return OPS[op](state, args);
  }

  // ---- Số liệu cho màn hình ----
  const companyAccounts = state => state.accounts.filter(item => item.owner === 'company');
  const countable = (state, txn) => !isPrivate(state, txn) && txn.match?.sheet !== 'noi_bo';
  /** Một ví: số dư đồng, USD chờ đổi, tuổi âm, cảnh báo. */
  function walletView(state, walletId) {
    const wallet = walletById(state, walletId);
    const balance = walletBalance(state, walletId);
    const age = balance < 0n && wallet.negSince ? daysBetween(wallet.negSince, state.clock) : 0;
    const alerts = [];
    if (balance < -wallet.limit) alerts.push(`Ví âm quá hạn mức ${money(wallet.limit)}`);
    if (balance < 0n && age > WALLET_AGE_DAYS) alerts.push(`Ví âm đã ${age} ngày, quá ${WALLET_AGE_DAYS} ngày`);
    return { id: wallet.id, name: wallet.name, balance, pendingUsd: walletPendingUsd(state, walletId), limit: wallet.limit, age, alerts, negative: balance < 0n };
  }
  /** Đòn bẩy của sếp: tiền đang có, đang ứng, vào/ra hôm nay, "Cần sếp". Không tính tài khoản cá nhân và cặp nội bộ. */
  function dongTien(state) {
    const accounts = companyAccounts(state).map(item => ({ id: item.id, name: item.short, currency: item.currency, balance: balanceOf(state, item.id), kind: item.kind }));
    const sumOf = currency => accounts.filter(item => item.currency === currency).reduce((sum, item) => sum + item.balance, 0n);
    const today = { vao: 0n, ra: 0n, vaoUsd: 0n, raUsd: 0n };
    for (const txn of state.txns) {
      if (dayOf(txn.time) !== state.today || !countable(state, txn)) continue;
      const key = txn.currency === 'USD' ? (txn.dir === 'in' ? 'vaoUsd' : 'raUsd') : (txn.dir === 'in' ? 'vao' : 'ra');
      today[key] += txn.amount;
    }
    let owed = 0n;
    for (const wallet of state.wallets) { const balance = walletBalance(state, wallet.id); if (balance < 0n) owed -= balance; }
    const waiting = state.requests.filter(request => request.status === 'cho_duyet').length;
    const unapproved = state.flags.filter(flag => flag.open && UNAPPROVED_FLAGS.includes(flag.type)).length;
    const unknown = exceptions(state).filter(item => item.kind === 'chua_ro').length;
    const personal = state.accounts.filter(item => item.owner === 'personal').map(item => ({ id: item.id, name: item.short, balance: balanceOf(state, item.id) }));
    return { accounts, vnd: sumOf('VND'), usd: sumOf('USD'), owed, today, personal,
      canSep: { waiting, unapproved, unknown, total: waiting + unapproved + unknown } };
  }

  const valueForSort = (state, txn) => (txn.currency === 'USD' ? usdToVnd(txn.amount, state.rates.bank) : txn.amount);
  /** Hộp ngoại lệ: khoản máy không chắc, xếp theo số tiền lớn trước. `kind`: chua_ro, lech, goi_y, nhieu, chi_chua_de_nghi. */
  function exceptions(state) {
    const out = [];
    for (const txn of state.txns) {
      if (isPrivate(state, txn)) continue;
      const what = `${money(txn.amount, txn.currency)} · ${txn.counterparty}`;
      if (txn.dir === 'in' && !txn.match) {
        const hint = txn.hint;
        if (hint?.kind === 'lech') {
          const receipt = state.receipts.find(item => item.id === hint.receiptId);
          out.push({ txn, amountText: money(txn.amount, txn.currency), kind: 'lech', title: 'Tiền về lệch so với phiếu',
            text: `${what}. Phiếu ${receipt.id} của ${customerById(state, hint.customerId).name} ghi ${money(receipt.amount)}: hụt ${money(hint.short)}, quá mức phí ngân hàng.` });
        } else if (hint?.kind === 'goi_y') {
          out.push({ txn, amountText: money(txn.amount, txn.currency), kind: 'goi_y', title: 'Có thể là tổng nhiều phiếu', text: `${what}. Bằng tổng phiếu ${hint.receiptIds.join(' + ')} của ${customerById(state, hint.customerId).name}. Kế toán xác nhận.` });
        } else if (hint?.kind === 'nhieu') {
          out.push({ txn, amountText: money(txn.amount, txn.currency), kind: 'nhieu', title: 'Có hơn một nơi để ghép', text: `${what}. Luật ${hint.rule} thấy ${hint.count} nơi; kế toán chọn.` });
        } else {
          out.push({ txn, amountText: money(txn.amount, txn.currency), kind: 'chua_ro', title: 'Tiền về chưa rõ của ai', text: `${what}. Nội dung: ${txn.content}.` });
        }
      } else if (txn.dir === 'out' && txn.match?.rule === null) {
        out.push({ txn, amountText: money(txn.amount, txn.currency), kind: 'chi_chua_de_nghi', title: 'Chi chưa có đề nghị', text: `${what}. Nội dung: ${txn.content}.` });
      }
    }
    return out.sort((a, b) => cmpDesc(valueForSort(state, a.txn), valueForSort(state, b.txn)));
  }

  const FLAG_TEXT = { chi_chua_duyet: 'Chi chưa có đề nghị duyệt', chuyen_truoc_duyet: 'Chuyển tiền khi đề nghị chưa được duyệt', khac_so: 'Số chuyển khác số đề nghị',
    khac_nguoi_nhan: 'Người nhận khác đề nghị', chi_hai_lan: 'Một đề nghị bị chi hai lần', kiem_quy_lech: 'Kiểm quỹ lệch' };
  /** Mọi cờ đang mở, mỗi cờ có chữ, số tiền và có gỡ được bằng duyệt bù không. */
  function openFlags(state) {
    return state.flags.filter(flag => flag.open).map(flag => {
      const txn = flag.txnId ? txnById(state, flag.txnId) : null;
      return { id: flag.id, type: flag.type, title: FLAG_TEXT[flag.type], clearable: UNAPPROVED_FLAGS.includes(flag.type), txnId: flag.txnId ?? null,
        text: txn ? `${money(txn.amount, txn.currency)} · ${txn.counterparty} · ${clock(txn.time)}` : `Lệch ${money(flag.diff)}` };
    });
  }
  /** Cảnh báo ví âm (quá hạn mức, quá lâu) của mọi ví. */
  const walletAlerts = state => state.wallets.flatMap(wallet => walletView(state, wallet.id).alerts.map(text => `${wallet.name}: ${text}`));

  const labelOfRule = txn => (txn.match?.rule ? RULE_TEXT[txn.match.rule] ?? txn.match.rule : txn.match ? 'Chưa có đề nghị' : 'Chưa ghép');
  /** Dòng sổ tiền cho một giao dịch. Việc riêng: bỏ người đối ứng và nội dung, giữ số tiền (chủ tài khoản xem được thì `owner` bật). */
  function txnRow(state, txn, { owner = false } = {}) {
    const hidden = isPrivate(state, txn) && !owner;
    const sheet = txn.match ? SHEETS[txn.match.sheet] ?? '' : 'Chưa ghép';
    const target = [];
    if (txn.match?.customerId) target.push(customerById(state, txn.match.customerId).name);
    if (txn.match?.walletId) target.push(walletById(state, txn.match.walletId).name);
    if (txn.match?.requestId) target.push(`đề nghị ${requestById(state, txn.match.requestId).code}`);
    if (txn.match?.category && txn.match.sheet === 'chi' && txn.match.rule !== null) target.push(txn.match.category);
    if (txn.match?.kind === 'doi_tien') target.push('bán USD');
    if (txn.match?.kind === 'chuyen_noi_bo') target.push('chuyển giữa tài khoản');
    return { id: txn.id, time: txn.time, clock: clock(txn.time), account: account(state, txn.accountId).short, dir: txn.dir, currency: txn.currency,
      amountText: signedMoney(txn.amount, txn.currency, txn.dir), who: hidden ? 'Việc riêng' : txn.counterparty, content: hidden ? '' : txn.content, private: isPrivate(state, txn),
      sheet, target: target.join(' · '), rule: isPrivate(state, txn) ? 'Không vào thống kê' : labelOfRule(txn), fee: txn.match?.fee ? `Phí ngân hàng ${money(txn.match.fee, txn.currency)}` : '',
      unresolved: unresolved(txn) && !isPrivate(state, txn) };
  }
  const txnRows = (state, options = {}) => [...state.txns].sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0))
    .filter(txn => !options.accountId || txn.accountId === options.accountId).map(txn => txnRow(state, txn, options));

  const accountsView = state => state.accounts.map(item => ({ id: item.id, name: item.short, currency: item.currency, balance: balanceOf(state, item.id), balanceText: money(balanceOf(state, item.id), item.currency),
    private: item.owner === 'personal', cash: item.kind === 'cash' }));

  /** Tháng này theo danh mục: số nền từ đầu tháng tới hôm qua + hôm nay. Chỉ đồng; thu theo khách, chi theo loại chi (không tính ví khách TQ và cặp nội bộ). */
  function monthByCategory(state) {
    const thu = { ...FX.monthBase.thu };
    const chi = { ...FX.monthBase.chi };
    for (const txn of state.txns) {
      if (txn.currency !== 'VND' || dayOf(txn.time) !== state.today || !txn.match) continue;
      if (txn.match.sheet === 'thu' && txn.match.customerId) { const name = customerById(state, txn.match.customerId).name; thu[name] = (thu[name] ?? 0n) + txn.amount; }
      if (txn.match.sheet === 'chi') chi[txn.match.category] = (chi[txn.match.category] ?? 0n) + txn.amount;
    }
    for (const fee of state.fees) chi['Phí ngân hàng'] = (chi['Phí ngân hàng'] ?? 0n) + (fee.currency === 'USD' ? usdToVnd(fee.amount, state.rates.bank) : fee.amount);
    const bars = group => {
      const entries = Object.entries(group).sort((a, b) => cmpDesc(a[1], b[1]));
      const top = entries.length ? entries[0][1] : 1n;
      return entries.map(([name, amount]) => ({ name, amount, text: money(amount), pct: Number((amount * 100n) / (top > 0n ? top : 1n)) }));
    };
    return { thu: bars(thu), chi: bars(chi) };
  }

  /** Sao kê một ví: số dư đầu ngày, từng dòng với số còn lại; USD chờ đổi ghi riêng. */
  function walletStatement(state, walletId) {
    const wallet = walletById(state, walletId);
    let balance = wallet.opening;
    const rows = [{ id: 'open', clock: '', label: 'Số dư đầu ngày', detail: '', deltaText: '', afterText: money(balance), after: balance }];
    for (const line of [...wallet.lines].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0))) {
      if (line.type === 'vao') {
        if (line.converted) balance += line.vnd;
        const waiting = `${usdText(line.usd)} đang chờ bán lấy đồng`;
        const detail = !line.converted ? '' : line.usd > 0n ? `${usdText(line.usd)} × tỷ giá tính khách ${F.full(line.rate)}/USD` : 'Tiền đồng vào ví';
        rows.push({ id: line.id, clock: clock(line.time), label: line.converted ? 'Tiền hàng vào ví' : 'USD về, chờ bán', detail: line.converted ? detail : waiting,
          deltaText: line.converted ? `+${money(line.vnd)}` : '—', afterText: money(balance), after: balance });
      } else {
        balance -= line.vnd;
        const request = requestById(state, line.requestId);
        rows.push({ id: line.id, clock: clock(line.time), label: line.type === 'ung' ? 'Ứng tiền mặt' : 'Chi hộ nhà cung cấp', detail: `${request.code} · ${payeeById(state, request.payeeId).name}`,
          deltaText: `−${money(line.vnd)}`, afterText: money(balance), after: balance });
      }
    }
    return rows;
  }
  /** Chênh giữa tỷ giá ngân hàng và tỷ giá tính khách của các lần đã đổi (chỉ để xem; chưa tính là thu hay không, câu hỏi 3 của spec). */
  const exchangeNote = state => state.exchanges.map(item => ({ usdText: usdText(item.usd), vndText: money(item.vnd), rateText: `${F.full(item.rate)}/USD`,
    customerRateText: `${F.full(state.rates.customer)}/USD`, gapText: money(item.vnd - usdToVnd(item.usd, state.rates.customer)) }));

  const expectationRows = state => state.expectations.map(item => ({ id: item.id, name: walletById(state, item.walletId).name, amountText: money(item.amount, item.currency), note: item.note,
    status: item.status, statusText: item.status === 've' ? (item.fee > 0n ? `Về rồi · phí ngân hàng ${money(item.fee, item.currency)}` : 'Về rồi') : 'Đang chờ' }));

  /** Một đề nghị cho màn hình: dòng thời gian bốn mốc, kiểm ví, chữ trạng thái. */
  function requestView(state, id) {
    const request = requestById(state, id);
    if (!request) return null;
    const payee = payeeById(state, request.payeeId);
    const check = request.status === 'cho_duyet' || (request.status !== 'tu_choi' && request.paid === 0n) ? walletCheck(state, request) : null;
    const event = what => request.events.find(item => item.what === what);
    const steps = [
      { id: 'tao', label: 'Tạo', event: event('tao') },
      { id: 'duyet', label: request.status === 'tu_choi' ? 'Từ chối' : 'Duyệt', event: event('duyet') ?? event('tu_choi') },
      { id: 'chuyen', label: 'Chuyển', event: event('chuyen') },
      { id: 'khop', label: 'Khớp ngân hàng', event: request.status === 'da_khop' ? request.events.filter(item => item.what === 'khop').pop() : null },
    ].map(step => ({ ...step, done: Boolean(step.event), at: step.event ? clock(step.event.at) : '', by: step.event?.by ?? '', text: step.event?.text ?? '' }));
    const partial = request.paid > 0n && request.paid < request.amount ? `Mới chuyển ${money(request.paid)} / ${money(request.amount)}` : '';
    return { id: request.id, code: request.code, type: request.type, typeText: TYPES[request.type], status: request.status, statusText: partial && request.status !== 'da_khop' ? partial : STATUS_TEXT[request.status],
      amountText: money(request.amount), payee: payee.name, category: payee.category, container: request.container, note: request.note, attachment: request.attachment, by: request.by, steps,
      transferText: `${request.code} ${payee.name}`, reason: request.reason ?? '', comments: request.comments.map(item => ({ ...item, clock: clock(item.at) })), wallet: check ? { name: check.name, balanceText: money(check.balance),
        afterText: money(check.after), over: check.over, overLimit: check.overLimit, limitText: money(check.limit) } : null, remainingText: money(remaining(request)) };
  }
  const requestList = state => state.requests.map(request => requestView(state, request.id));
  const approvedWaiting = state => state.requests.filter(request => (request.status === 'da_duyet' || request.status === 'da_chuyen') && request.type !== 'ung_tien_mat').map(request => requestView(state, request.id));
  const cashWaiting = state => state.requests.filter(request => request.status === 'da_duyet' && request.type === 'ung_tien_mat').map(request => requestView(state, request.id));
  const pendingApproval = state => state.requests.filter(request => request.status === 'cho_duyet').map(request => requestView(state, request.id));
  /** Phiếu thu điền sẵn cho team công nợ (chỉ xem trong bản thử, không ghi sổ nợ). */
  const draftRows = state => state.drafts.map(draft => ({ id: draft.id, customer: customerById(state, draft.customerId).name, amountText: money(draft.amount), date: draft.date, reference: draft.reference }));
  const cashView = state => ({ balance: balanceOf(state, 'quy'), balanceText: money(balanceOf(state, 'quy')),
    counts: state.counts.map(item => ({ clock: clock(item.time), countedText: money(item.counted), expectedText: money(item.expected), diff: item.diff,
      diffText: item.diff === 0n ? 'Khớp' : `Lệch ${money(item.diff)}` })) });
  const feeRows = state => state.fees.map(fee => ({ amountText: money(fee.amount, fee.currency), text: `Phí ngân hàng ${money(fee.amount, fee.currency)} tách khỏi giao dịch ${fee.txnId}` }));

  // ---- Kịch bản một ngày: nhật ký thao tác để lùi được ----
  const fixtureTag = { chi_thuong: 'r1', chi_ho: 'r2', ung_tien_mat: 'r3' };
  const byTag = (state, tag) => state.requests.find(request => request.tag === tag);
  const at = time => `${FX.TODAY} ${time}`;

  const STEPS = [
    { n: 1, time: '08:05', role: 'ketoan', tab: 'ngoai-le', title: 'Sao kê sáng về, máy ghép',
      text: 'Sao kê sáng của các tài khoản về. Máy ghép phần lớn vào bốn sổ; vài khoản không chắc nằm ở hộp ngoại lệ.',
      human: 'Không cần bấm gì: bấm Tiếp để sao kê về.',
      done: state => state.txns.some(txn => txn.id === 'g01'),
      auto: sim => act(sim, 'importTxns', { time: at('08:05'), txns: FX.morningStatement }) },
    { n: 2, time: '08:30', role: 'ketoan', tab: 'ngoai-le', title: 'Kế toán gắn khoản chưa rõ cho khách',
      text: 'Một khoản tiền về chưa rõ của ai, hóa ra là bên thứ ba trả hộ Khách A. Kế toán gắn khách; máy hỏi có nhớ người chuyển không; phiếu thu điền sẵn hiện ở việc của team công nợ.',
      human: 'Ở hộp ngoại lệ, chọn "Khách A" cho khoản 12.000.000 đ rồi bấm Gắn khách.',
      done: state => state.drafts.some(draft => draft.reference === 'g08') || !state.txns.some(txn => txn.id === 'g08' && !txn.match),
      auto: sim => act(sim, 'attachInflow', { txnId: 'g08', customerId: 'kh-a', remember: true, time: at('08:30') }) },
    { n: 3, time: '09:00', role: 'nhanvien', tab: 'tao', title: 'Nhân viên tạo đề nghị chi',
      text: 'Nhân viên tạo đề nghị phí nâng hạ, gắn container MAUU1000101, kèm ảnh hóa đơn giả. Bot (mô phỏng) báo sếp.',
      human: 'Ở màn Nhân viên, bấm "Điền ví dụ" rồi Gửi đề nghị.',
      done: state => Boolean(byTag(state, 'r1')),
      auto: sim => act(sim, 'createRequest', { ...FX.scenario.request1, tag: 'r1', time: at('09:00') }) },
    { n: 4, time: '09:31', role: 'sep', tab: 'dong-tien', title: 'Sếp duyệt',
      text: 'Sếp mở Dòng tiền trên điện thoại, thấy thẻ đề nghị chờ duyệt và bấm Duyệt.',
      human: 'Ở màn Sếp, bấm Duyệt trên thẻ đề nghị.',
      done: state => Boolean(byTag(state, 'r1')) && byTag(state, 'r1').status !== 'cho_duyet',
      auto: sim => act(sim, 'approveRequest', { id: byTag(sim.state, 'r1').id, role: 'sep', time: at('09:31') }) },
    { n: 5, time: '10:40', role: 'ketoan', tab: 'cho-chuyen', title: 'Kế toán chuyển, ngân hàng khớp',
      text: '10:40 kế toán chép nội dung chuyển khoản (có mã đề nghị) và chuyển. 10:42 giao dịch ra về sao kê, máy khớp và đóng đề nghị.',
      human: 'Ở Chờ chuyển, bấm Chép nội dung rồi Đã chuyển (mô phỏng).',
      done: state => byTag(state, 'r1')?.status === 'da_khop',
      auto: sim => {
        const request = byTag(sim.state, 'r1');
        if (request.status === 'da_duyet') act(sim, 'markTransferred', { id: request.id, time: at('10:40') });
        if (request.paid < request.amount) {
          act(sim, 'importTxns', { time: at('10:42'), txns: [{ ...FX.scenario.transfer1, amount: remaining(request), counterparty: payeeById(sim.state, request.payeeId).name, content: `${request.code} PHI NANG HA` }] });
        }
      } },
    { n: 6, time: '11:00', role: 'tienhang', tab: 'cho-ve', title: 'Ghi tiền chờ về',
      text: 'Người lo tiền hàng ghi: Khách TQ 2 báo sẽ chuyển 8.000 USD vào tài khoản đô la hôm nay.',
      human: 'Ở màn Tiền hàng, mục Tiền chờ về, ghi 8.000 USD cho Khách TQ 2.',
      done: state => state.expectations.length > 0,
      auto: sim => act(sim, 'createExpectation', { ...FX.scenario.expectation, time: at('11:00') }) },
    { n: 7, time: '14:06', role: 'tienhang', tab: 'vi', title: 'USD tiền hàng về, bán USD',
      text: '14:06 USD của Khách TQ 1 về qua công ty chuyển đã biết: vào ví. 14:20 bán USD, ví cộng tiền đồng theo tỷ giá tính khách. 14:40 USD của Khách TQ 2 về: tiền chờ báo "Về rồi" (phí ngân hàng đã tách).',
      human: 'Không cần bấm gì: bấm Tiếp để sao kê chiều về.',
      done: state => state.txns.some(txn => txn.id === 'g34'),
      auto: sim => {
        act(sim, 'importTxns', { time: at('14:06'), txns: [FX.scenario.usdIn1] });
        act(sim, 'importTxns', { time: at('14:20'), txns: FX.scenario.usdSell });
        act(sim, 'importTxns', { time: at('14:40'), txns: [FX.scenario.usdIn2] });
      } },
    { n: 8, time: '14:30', role: 'sep', tab: 'dong-tien', title: 'Chi hộ Khách TQ 1, ba lệnh một đề nghị',
      text: 'Đề nghị chi hộ Khách TQ 1 cho Nhà vườn 1; sếp duyệt. Ngân hàng chuyển ba lệnh, máy khớp cả ba vào một đề nghị; ví Khách TQ 1 trừ.',
      human: 'Tạo đề nghị chi hộ (Nhân viên) rồi sếp Duyệt; hoặc bấm Tiếp.',
      done: state => byTag(state, 'r2')?.status === 'da_khop',
      auto: sim => {
        if (!byTag(sim.state, 'r2')) act(sim, 'createRequest', { ...FX.scenario.request2, tag: 'r2', time: at('14:30') });
        const request = byTag(sim.state, 'r2');
        if (request.status === 'cho_duyet') act(sim, 'approveRequest', { id: request.id, role: 'sep', time: at('14:45') });
        act(sim, 'importTxns', { time: at('15:08'), txns: FX.scenario.transfers2 });
      } },
    { n: 9, time: '15:20', role: 'sep', tab: 'dong-tien', title: 'Một khoản chi không có đề nghị',
      text: 'Ngân hàng báo một khoản chi không có đề nghị nào: cờ đỏ. Chỉ sếp có nút Duyệt bù; kế toán và người chuyển không tự gỡ được.',
      human: 'Ở màn Sếp, bấm Duyệt bù trên cờ đỏ nếu sếp đồng ý khoản chi.',
      done: state => state.txns.some(txn => txn.id === 'g51'),
      auto: sim => act(sim, 'importTxns', { time: at('15:20'), txns: [FX.scenario.noRequest] }) },
    { n: 10, time: '16:00', role: 'ketoan', tab: 'quy', title: 'Ứng tiền mặt vượt số dư ví',
      text: 'Đề nghị ứng 30.000.000 đ tiền mặt cho người của Khách TQ 2, vượt số dư ví: thẻ ghi rõ; sếp duyệt; thủ quỹ giao kèm ảnh biên bản giả. Quỹ trừ, ví âm thêm, tổng đang ứng tăng.',
      human: 'Sếp duyệt; thủ quỹ chọn "Có ảnh biên bản" rồi bấm Giao tiền mặt.',
      done: state => byTag(state, 'r3')?.status === 'da_khop',
      auto: sim => {
        if (!byTag(sim.state, 'r3')) act(sim, 'createRequest', { ...FX.scenario.request3, tag: 'r3', time: at('16:00') });
        const request = byTag(sim.state, 'r3');
        if (request.status === 'cho_duyet') act(sim, 'approveRequest', { id: request.id, role: 'sep', time: at('16:10') });
        if (request.status !== 'da_khop') act(sim, 'handOverCash', { id: request.id, photo: true, time: at('16:20') });
      } },
    { n: 11, time: '17:30', role: 'ketoan', tab: 'quy', title: 'Kiểm quỹ cuối ngày',
      text: 'Thủ quỹ đếm tiền mặt và ghi số. Số đếm bằng số sổ thì khớp; lệch thì có cờ.',
      human: 'Ở Quỹ tiền mặt, gõ số đếm được rồi bấm Ghi số đếm.',
      done: state => state.counts.length > 0,
      auto: sim => act(sim, 'countCash', { counted: balanceOf(sim.state, 'quy'), time: at('17:30') }) },
  ];

  const newSim = () => ({ state: baseState(), log: [], cursor: 0, last: null });
  /** Chạy một thao tác và ghi vào nhật ký (kèm bước đang đứng) nếu thành công. Đề nghị nhân viên tạo tay nhận nhãn bước đang chờ nếu chưa có. */
  function act(sim, op, args) {
    const input = { ...args };
    if (op === 'createRequest' && !input.tag && fixtureTag[input.type] && !byTag(sim.state, fixtureTag[input.type])) input.tag = fixtureTag[input.type];
    const result = run(sim.state, op, input);
    if (result.ok) sim.log.push({ at: sim.cursor, op, args: input });
    sim.last = result;
    return result;
  }
  const stepNow = sim => STEPS[sim.cursor] ?? null;
  /** Bấm Tiếp: làm nốt phần chưa làm của bước hiện tại rồi sang bước sau. */
  function next(sim) {
    const step = stepNow(sim);
    if (!step) return false;
    if (!step.done(sim.state)) step.auto(sim);   // việc người đã bấm tay thì không làm lại
    sim.cursor += 1;
    return true;
  }
  /** Bấm Trước: bỏ mọi thao tác từ bước vừa xong (kể cả người bấm tay ở bước đang chờ), dựng lại từ đầu ngày. */
  function back(sim) {
    if (sim.cursor === 0) return false;
    const target = sim.cursor - 1;
    const keep = sim.log.filter(entry => entry.at < target);
    sim.state = baseState();
    sim.log = [];
    sim.cursor = 0;
    for (const entry of keep) {
      sim.cursor = entry.at;
      run(sim.state, entry.op, entry.args);
      sim.log.push(entry);
    }
    sim.cursor = target;
    return true;
  }
  const reset = sim => { sim.state = baseState(); sim.log = []; sim.cursor = 0; sim.last = null; };
  const stepStatus = (sim, index) => (index < sim.cursor ? 'xong' : index === sim.cursor ? (STEPS[index].done(sim.state) ? 'da-lam-tay' : 'dang-cho') : 'chua-toi');
  const lastBot = state => (state.bot.length ? state.bot[state.bot.length - 1] : null);
  /** Tin bot (mô phỏng) nhắc tới một mã đề nghị. */
  const botFor = (state, code) => state.bot.filter(item => item.text.includes(code)).map(item => ({ clock: clock(item.time), to: item.to, text: item.text }));
  /** Danh mục để chọn trong biểu mẫu: khách, người nhận, khách Trung Quốc. */
  const directory = state => ({ customers: state.customers.map(item => ({ id: item.id, name: item.name })), payees: state.payees.map(item => ({ id: item.id, name: item.name })),
    wallets: state.wallets.map(item => ({ id: item.id, name: item.name })) });

  return { ROLES, STEPS, SHEETS, TYPES, STATUS_TEXT, RULE_TEXT, MATCH_BEFORE_DAYS, MATCH_AFTER_DAYS, FEE_LIMIT, WALLET_AGE_DAYS, UNAPPROVED_FLAGS,
    money, usdText, parseAmount, parseDollars, parseCount, usdToVnd, daysBetween, clock,
    baseState, run, findMatch, autoMatch, balanceOf, walletBalance, walletCheck, walletView, walletStatement, exchangeNote, dongTien, exceptions, openFlags, walletAlerts,
    txnRows, accountsView, monthByCategory, expectationRows, requestView, requestList, approvedWaiting, cashWaiting, pendingApproval, draftRows, cashView, feeRows,
    newSim, act, next, back, reset, stepNow, stepStatus, lastBot, botFor, directory, fixtureTag };
})();
if (typeof module !== 'undefined') module.exports = ThuChiTuSinhModel;
