// Bản xem Tổng quan v4 (DASH-06) — dữ liệu giả: tên "Mẫu …" và mọi số tiền đều hư cấu. Mười hai khách lấy đúng số trên bản đề xuất
// "Khách cần đòi trước" của team ngày 6/11/2026 (quá hạn, còn nợ, số ngày trả và đi hàng); phần tháng nợ và 12 tháng thêm vào để mọi
// khối cộng về cùng một tổng. Đơn vị: triệu đồng. Hôm nay 06/11/2026; hạn trả: nợ tháng M đến hạn cuối tháng M+1 (DASH-03).
// months: còn nợ theo tháng nợ "YYYY-MM" sau khi tiền thu đã trừ nợ cũ trước. payDays / tripDays: số ngày từ lần trả / chuyến
// gần nhất, null = chưa trả lần nào / chưa có chuyến. Chuyến 20 ngày trước của Mẫu Tân Tiến chưa có giá nên không có trong months.
window.MOCK = {
  asOf: '2026-11-06',
  updatedAt: '10:05',
  rule: { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, active_trip_days: 30 },
  missingPriceTrips: 3,
  customers: [
    { id: 1, name: 'Mẫu Đông Á', commodity: 'Sầu riêng cảng', payDays: 3, tripDays: 2,
      months: { '2026-02': 1500, '2026-03': 1800, '2026-05': 1500, '2026-06': 2000, '2026-07': 2500, '2026-08': 2400, '2026-09': 3000, '2026-10': 3900, '2026-11': 900 } },
    { id: 2, name: 'Mẫu Gia Lai', commodity: 'Sầu riêng bộ', payDays: 95, tripDays: 0,
      months: { '2026-03': 1500, '2026-05': 1500, '2026-07': 1600, '2026-08': 1500, '2026-09': 1800, '2026-10': 2200, '2026-11': 600 } },
    { id: 3, name: 'Mẫu An Phát', commodity: 'Thanh long', payDays: 7, tripDays: 5,
      months: { '2026-02': 750, '2026-06': 750, '2026-07': 1200, '2026-08': 1000, '2026-09': 1300, '2026-10': 2000, '2026-11': 400 } },
    { id: 4, name: 'Mẫu Cửu Long', commodity: 'Sầu riêng cảng', payDays: 215, tripDays: 170,
      months: { '2026-02': 1100, '2026-03': 1000, '2026-05': 1100 } },
    { id: 5, name: 'Hộ KD Mẫu Hòa Bình', commodity: 'Chuối', payDays: 70, tripDays: 80,
      months: { '2026-06': 950, '2026-07': 1200, '2026-08': 250 } },
    { id: 6, name: 'Mẫu Bình Minh', commodity: 'Thanh long', payDays: 8, tripDays: 2,
      months: { '2026-07': 800, '2026-08': 500, '2026-09': 800, '2026-10': 700, '2026-11': 200 } },
    { id: 7, name: 'Mẫu Kim Ngân', commodity: 'Dừa', payDays: 125, tripDays: 85,
      months: { '2026-07': 470, '2026-08': 300 } },
    { id: 8, name: 'Mẫu Lộc Phát', commodity: 'Chuối', payDays: 95, tripDays: 95,
      months: { '2026-07': 400, '2026-08': 270 } },
    { id: 9, name: 'Mẫu Minh Châu', commodity: 'Xoài', payDays: 40, tripDays: 20,
      months: { '2026-08': 240, '2026-09': 400, '2026-10': 90 } },
    { id: 10, name: 'Mẫu Nam Việt', commodity: 'Dừa', payDays: 300, tripDays: 325,
      months: { '2025-12': 631 } },
    { id: 11, name: 'Mẫu Tân Tiến', commodity: 'Bán cước', payDays: null, tripDays: 20,
      months: { '2026-09': 83 } },
    { id: 12, name: 'Mẫu Thái Bình', commodity: 'Xoài', payDays: 9, tripDays: 4,
      months: { '2026-11': 160 } },
  ],
  // 12 tháng cả công ty: phát sinh, đã thu (cộng dòng Tổng tháng của mọi sổ, DA-THU-01) và còn phải thu cuối tháng; tháng 11 tính tới 06/11.
  // Còn phải thu cuối tháng 11/2025 (trước cửa sổ) là 36.684; mỗi tháng: cuối tháng trước + phát sinh − đã thu.
  months: [
    { month: '2025-12', charges: 7800, received: 7500, end: 36984 },
    { month: '2026-01', charges: 8200, received: 7900, end: 37284 },
    { month: '2026-02', charges: 7400, received: 6100, end: 38584 },
    { month: '2026-03', charges: 8100, received: 8600, end: 38084 },
    { month: '2026-04', charges: 7600, received: 7400, end: 38284 },
    { month: '2026-05', charges: 8300, received: 7200, end: 39384 },
    { month: '2026-06', charges: 8800, received: 7600, end: 40584 },
    { month: '2026-07', charges: 9600, received: 7900, end: 42284 },
    { month: '2026-08', charges: 9200, received: 7700, end: 43784 },
    { month: '2026-09', charges: 9900, received: 7800, end: 45884 },
    { month: '2026-10', charges: 10400, received: 8100, end: 48184 },
    { month: '2026-11', charges: 2260, received: 1200, end: 49244 },
  ],
};
