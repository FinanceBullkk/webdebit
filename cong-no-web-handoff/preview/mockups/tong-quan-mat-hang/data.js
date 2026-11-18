/* Bản xem "công nợ theo mặt hàng" trên Tổng quan — DỮ LIỆU GIẢ: khách "Mẫu …", số tiền hư cấu.
   Chặn fetch của trang thật (dashboard-v7.js) và trả API giả có tổng khớp nhau, để trang thật chạy đủ lọc. */
(() => {
  'use strict';
  const AS_OF = '2026-11-09';
  const rule = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
  const TR = 1_000_000n;
  // [mặt hàng, cảng/bộ, [5 nhóm hạn trả, triệu], ngày từ lần trả, ngày từ chuyến]
  const SPEC = [
    ['Sầu riêng', 'CANG', [820, 640, 1310, 260, 0], 12, 3], ['Sầu riêng', 'CANG', [410, 380, 520, 0, 0], 8, 5],
    ['Sầu riêng', 'CANG', [0, 0, 160, 420, 180], 140, 120], ['Sầu riêng', 'CANG', [260, 190, 0, 0, 0], 4, 2],
    ['Sầu riêng', 'CANG', [120, 90, 210, 0, 0], 25, 9], ['Sầu riêng', 'CANG', [0, 0, 0, 0, 95], null, 400],
    ['Sầu riêng', 'BO', [530, 410, 380, 120, 0], 18, 4], ['Sầu riêng', 'BO', [240, 160, 90, 0, 0], 6, 6],
    ['Sầu riêng', 'BO', [0, 0, 70, 210, 0], 95, 33], ['Sầu riêng', 'BO', [140, 60, 0, 0, 0], 11, 1],
    ['Chuối', null, [380, 310, 240, 0, 0], 9, 2], ['Chuối', null, [210, 150, 0, 0, 0], 5, 3],
    ['Chuối', null, [0, 0, 120, 160, 60], 210, 150], ['Chuối', null, [95, 70, 45, 0, 0], 20, 7],
    ['Mít', null, [180, 140, 160, 0, 0], 14, 5], ['Mít', null, [0, 0, 50, 140, 0], 70, 20],
    ['Mít', null, [75, 60, 0, 0, 0], 3, 2],
    ['Thanh long', null, [120, 90, 60, 0, 0], 16, 8], ['Thanh long', null, [0, 0, 0, 80, 40], null, 260],
    ['Dừa', null, [90, 70, 30, 0, 0], 10, 4], ['Dừa', null, [40, 0, 0, 0, 0], 2, 1],
    ['Chanh dây', null, [60, 40, 20, 0, 0], 22, 12],
    ['Khoai lang', null, [18, 10, 0, 0, 0], 7, 6], ['Gừng', null, [0, 0, 12, 9, 0], 120, 95],
    [null, null, [0, 0, 40, 60, 110], null, 300], ['Sầu riêng', null, [30, 20, 25, 0, 0], 30, 15],
  ];
  const day = back => { const d = new Date(`${AS_OF}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - back); return d.toISOString().slice(0, 10); };
  const month = back => { const d = new Date(`${AS_OF.slice(0, 7)}-01T00:00:00Z`); d.setUTCMonth(d.getUTCMonth() - back); return d.toISOString().slice(0, 10); };
  const BACK = [0, 1, 2, 4, 9];   // tháng nợ đại diện cho 5 nhóm hạn trả (đến hạn sau 1 tháng)
  const customers = SPEC.map(([commodity, mode, tiers, pay, trip], i) => {
    const v = tiers.map(x => BigInt(x) * TR + BigInt((i * 7919 + x * 13) % 1000) * 1000n * (x ? 1n : 0n));
    const total = v.reduce((s, x) => s + x, 0n);
    const overdue = v[2] + v[3] + v[4];
    const long = v[3] + v[4];
    const risk = overdue <= 0n ? 'ok' : long > 0n || pay == null || pay > rule.no_pay_days || trip == null || trip > rule.no_trip_days ? 'high' : 'watch';
    const months = v.map((x, t) => ({ month: month(BACK[t]), outstanding_vnd: String(x) })).filter(m => m.outstanding_vnd !== '0').reverse();
    return { customer_id: 101 + i, name: `Mẫu ${String(i + 1).padStart(2, '0')}`, commodity, transport_mode: mode,
      tiers_vnd: v.map(String), outstanding_vnd: String(total), overdue_vnd: String(overdue), long_overdue_vnd: String(long),
      oldest_open_month: months[0]?.month ?? null, risk, months,
      last_receipt_date: pay == null ? null : day(pay), last_receipt_exact: pay == null ? null : true, pay_days: pay,
      last_trip_date: trip == null ? null : day(trip), last_trip_exact: trip == null ? null : true, trip_days: trip };
  });
  const sum = list => list.reduce((s, x) => s + BigInt(x), 0n);
  const receivable = sum(customers.map(c => c.outstanding_vnd));
  const TIERS = ['not_due', 'due_this_month', 'late_1_2', 'late_3_6', 'late_over_6'];
  const high = customers.filter(c => c.risk === 'high');
  const debt = { as_of: AS_OF, month: `${AS_OF.slice(0, 7)}-01`, rule, receivable_vnd: String(receivable),
    due_tiers: TIERS.map((tier, t) => ({ tier, receivable_vnd: String(sum(customers.map(c => c.tiers_vnd[t]))) })),
    summary: { overdue_vnd: String(sum(customers.map(c => c.overdue_vnd))), long_overdue_vnd: String(sum(customers.map(c => c.long_overdue_vnd))),
      overdue_customers: customers.filter(c => BigInt(c.overdue_vnd) > 0n).length, high_customers: high.length,
      high_overdue_vnd: String(sum(high.map(c => c.overdue_vnd))) },
    this_month: { month: `${AS_OF.slice(0, 7)}-01`, charges_vnd: '2140000000', received_vnd: '1385000000' }, customers };
  const dashboard = { as_of: AS_OF, demo: false, receivable: { total_vnd: String(receivable), customers: customers.length },
    credit: { total_vnd: '-212000000', customers: 4 }, by_commodity: [], aging: [], top_debtors: [],
    todo: { missing_price: [{ customer_id: 103, name: 'Mẫu 03', count: 5 }], pending_review: [], no_baseline: [], credit: [] },
    today: { trips: 0, receipts: 0, received_vnd: '0', voids: 0, by_actor: [] } };
  const API = { '/api/v7/dashboard': dashboard, '/api/v7/dashboard/debt': debt,
    '/api/v7/customers': { customers: customers.map(c => ({ id: c.customer_id, name: c.name, commodity: c.commodity, transport_mode: c.transport_mode })) } };
  window.fetch = async url => {
    const path = new URL(String(url), location.href).pathname.replace(/^.*(\/api\/)/, '$1');
    const body = API[path];
    return { ok: body != null, status: body == null ? 404 : 200, json: async () => structuredClone(body ?? {}) };
  };
})();
