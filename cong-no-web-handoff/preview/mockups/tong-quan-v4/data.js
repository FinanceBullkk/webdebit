// Bản xem Tổng quan v4 (DASH-06) — dữ liệu giả: tên "Mẫu …" và mọi số tiền đều hư cấu, tổng tiền khác số thật. Chỉ tỷ trọng theo số đo
// trên `hao` ngày 6/11/2026 (spec, mục Số thật): 69 khách, chia 3 / 27 / 10 / 12 / 17; tiền quá hạn 2% / 22% / 28% / 48%; ba sổ từ 10%
// tiền quá hạn giữ 61%. Đơn vị: triệu đồng. Hôm nay 06/11/2026; hạn trả: nợ tháng M đến hạn cuối tháng M+1 (DASH-03).
// months: còn nợ theo tháng nợ "YYYY-MM" sau khi tiền thu đã trừ nợ cũ trước. payDays / tripDays: số ngày từ lần trả / chuyến
// gần nhất, null = chưa trả lần nào / chưa có chuyến.
(() => {
  // Mười sổ lớn nhất, đúng hình dạng đo được: sổ thứ hai có tình trạng "còn nợ cũ" chỉ vì 1% nợ từ 3 tháng.
  const top = [
    { name: 'Mẫu Đại Dương', commodity: 'Sầu riêng cảng', payDays: 12, tripDays: 3, months: { '2026-08': 5000, '2026-09': 8000, '2026-10': 4800, '2026-11': 1000 } },
    { name: 'Mẫu Hoàn Cầu', commodity: 'Sầu riêng cảng', payDays: 45, tripDays: 5, months: { '2026-07': 70, '2026-08': 2770, '2026-09': 4000, '2026-10': 2800, '2026-11': 510 } },
    { name: 'Mẫu Thái Dương', commodity: 'Sầu riêng bộ', payDays: 8, tripDays: 2, months: { '2026-08': 1400, '2026-09': 3000, '2026-10': 2300, '2026-11': 425 } },
    { name: 'Mẫu Cửu Long', commodity: 'Thanh long', payDays: 215, tripDays: 170, months: { '2026-03': 1000, '2026-05': 1000, '2026-06': 800 } },
    { name: 'Hộ KD Mẫu Hòa Bình', commodity: 'Chuối', payDays: 130, tripDays: 95, months: { '2026-06': 1400, '2026-08': 720 } },
    { name: 'Mẫu An Phát', commodity: 'Thanh long', payDays: 14, tripDays: 4, months: { '2026-06': 620, '2026-08': 560, '2026-09': 700, '2026-10': 900, '2026-11': 120 } },
    { name: 'Mẫu Nam Việt', commodity: 'Dừa', payDays: 300, tripDays: 325, months: { '2026-03': 600, '2026-08': 80 } },
    { name: 'Mẫu Lộc Phát', commodity: 'Chuối', payDays: 50, tripDays: 40, months: { '2026-05': 440, '2026-09': 160 } },
    { name: 'Mẫu Gia Lai', commodity: 'Sầu riêng bộ', payDays: 95, tripDays: 6, months: { '2026-06': 340, '2026-08': 220, '2026-10': 120 } },
    { name: 'Mẫu Kim Ngân', commodity: 'Dừa', payDays: 310, tripDays: 280, months: { '2025-12': 560 } },
  ];
  const COMMODITIES = ['Thanh long', 'Chuối', 'Dừa', 'Xoài', 'Bán cước'];
  const filler = (count, make) => Array.from({ length: count }, (_, i) => ({ commodity: COMMODITIES[i % COMMODITIES.length], ...make(i) }));
  const name = (kind, i) => `Mẫu ${kind} ${String(i + 1).padStart(2, '0')}`;
  const customers = [
    ...top,
    // Vẫn trả, quá hạn ngắn: thêm 10 khách, 180 triệu mỗi khách; một khách đã hơn 30 ngày không đi hàng.
    ...filler(10, i => ({ name: name('Bình An', i), payDays: 5 + i * 5, tripDays: i === 9 ? 40 : 3 + i * 2, months: { '2026-09': 180, '2026-10': 120 } })),
    // Vẫn trả, còn nợ cũ: thêm 7 khách.
    ...filler(7, i => ({ name: name('Hưng Thịnh', i), payDays: 10 + i * 6, tripDays: 7 + i * 8, months: { '2026-06': 100, '2026-09': i === 6 ? 160 : 170 } })),
    // Ngừng đi hàng, không trả: thêm 23 khách; 4 khách chưa trả lần nào, phần lớn đã hơn 180 ngày không đi hàng.
    ...filler(23, i => ({ name: name('Phú Quý', i), payDays: i < 4 ? null : 70 + i * 14, tripDays: 35 + i * 20, months: { [i % 2 ? '2026-03' : '2026-05']: i === 22 ? 110 : 115 } })),
    // Vẫn đi hàng, không trả: thêm 2 khách.
    { name: 'Mẫu Tân Tiến', commodity: 'Bán cước', payDays: null, tripDays: 22, months: { '2026-08': 120 } },
    { name: 'Mẫu Trường Sơn', commodity: 'Xoài', payDays: 70, tripDays: 10, months: { '2026-08': 120 } },
    // Không quá hạn: 17 khách.
    ...filler(17, i => ({ name: name('Thuận Lợi', i), payDays: i < 2 ? null : 4 + i * 3, tripDays: 2 + i, months: { '2026-10': 200 } })),
  ].map((customer, i) => ({ id: i + 1, ...customer }));

  // 12 tháng cả công ty: phát sinh, đã thu; còn phải thu cuối tháng tính lùi từ tổng còn nợ nên điểm cuối luôn bằng tổng (DA-THU-01).
  const flows = [['2025-12', 9000, 8700], ['2026-01', 9400, 9100], ['2026-02', 8500, 7000], ['2026-03', 9300, 9900], ['2026-04', 8700, 8500], ['2026-05', 9500, 8300],
    ['2026-06', 10100, 8700], ['2026-07', 11000, 9100], ['2026-08', 10600, 8900], ['2026-09', 11400, 9000], ['2026-10', 12000, 9300], ['2026-11', 2055, 1400]];
  const receivable = customers.reduce((sum, c) => sum + Object.values(c.months).reduce((a, b) => a + b, 0), 0);
  let end = receivable;
  const months = flows.map(([month, charges, received]) => ({ month, charges, received })).reverse().map(row => {
    const out = { ...row, end };
    end -= row.charges - row.received;
    return out;
  }).reverse();

  window.MOCK = {
    asOf: '2026-11-06',
    updatedAt: '10:05',
    // big_share_pct, big_max: mốc và số thẻ tối đa của hàng Sổ lớn (DASH-06).
    rule: { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, active_trip_days: 30, big_share_pct: 10, big_max: 4 },
    missingPriceTrips: 3,
    customers,
    months,
  };
})();
