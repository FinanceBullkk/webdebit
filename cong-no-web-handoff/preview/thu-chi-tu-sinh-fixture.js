/* THU-CHI-02 đợt 0: dữ liệu BỊA cho bản bấm thử "Thu chi tự sinh". Không phải dữ liệu thật: tên là "Khách A/B/C",
   "Khách TQ 1/2", "Công ty chuyển TQ 1/2", "Nhà vườn 1/2", "Hãng tàu X", "Cảng Y"; container chỉ có tiền tố MAUU; số tiền tròn.
   Tiền là số nguyên ở đơn vị nhỏ nhất (đồng; cent với USD), viết bằng BigInt. Hôm nay của bản thử cố định 24/11/2026. */
const ThuChiTuSinhFixture = (() => {
  'use strict';
  const TODAY = '2026-11-24';

  const companies = [
    { id: 'cty-a', name: 'Công ty A' },
    { id: 'cty-b', name: 'Công ty B' },
    { id: 'cty-xk', name: 'Công ty xuất khẩu' },
  ];

  // kind: bank | cash. owner: company | personal. `opening` là số dư đầu ngày hôm nay.
  const accounts = [
    { id: 'tk1', name: 'Công ty A · Ngân hàng 1', short: 'Ngân hàng 1 (đồng)', currency: 'VND', kind: 'bank', owner: 'company', company: 'cty-a', opening: 500000000n },
    { id: 'tk2', name: 'Công ty B · Ngân hàng 2', short: 'Ngân hàng 2 (đồng)', currency: 'VND', kind: 'bank', owner: 'company', company: 'cty-b', opening: 200000000n },
    { id: 'tk3', name: 'Công ty xuất khẩu · Đô la', short: 'Ngân hàng 3 (USD)', currency: 'USD', kind: 'bank', owner: 'company', company: 'cty-xk', opening: 2000000n },
    { id: 'tk4', name: 'Tài khoản cá nhân', short: 'Tài khoản cá nhân', currency: 'VND', kind: 'bank', owner: 'personal', company: null, opening: 30000000n },
    { id: 'quy', name: 'Quỹ tiền mặt', short: 'Quỹ tiền mặt', currency: 'VND', kind: 'cash', owner: 'company', company: 'cty-a', opening: 50000000n },
  ];

  // Tên đối tác của chính nhóm: dùng cho luật cặp nội bộ (R8).
  const ownNames = ['Công ty A', 'Công ty B', 'Công ty xuất khẩu', 'Quỹ tiền mặt'];

  const customers = [
    { id: 'kh-a', name: 'Khách A', code: 'HTH0001K' },
    { id: 'kh-b', name: 'Khách B', code: 'HTH0002K' },
    { id: 'kh-c', name: 'Khách C', code: 'HTH0003K' },
  ];

  // Ví khách Trung Quốc: số dư đầu ngày (đồng). Âm là công ty đang ứng. `limit` là hạn mức ứng, `negSince` ngày bắt đầu âm.
  const wallets = [
    { id: 'tq1', name: 'Khách TQ 1', opening: 150000000n, limit: 100000000n, negSince: null },
    { id: 'tq2', name: 'Khách TQ 2', opening: -20000000n, limit: 100000000n, negSince: '2026-11-10' },
  ];

  // Công ty chuyển tiền đã biết (R3): tên người chuyển → nơi ghép.
  const payers = {
    'Khách C': { sheet: 'thu', customerId: 'kh-c' },
    'Công ty chuyển TQ 1': { sheet: 'vi', walletId: 'tq1' },
  };
  const unknownPayers = ['Công ty chuyển TQ 2', 'Bên thứ ba 1'];

  // Người nhận chi: danh mục đối tác. `standing` = sếp đã duyệt định kỳ (R9), khỏi đề nghị từng lần.
  const payees = [
    { id: 'cang-y', name: 'Cảng Y', category: 'Phí nâng hạ', standing: false },
    { id: 'hang-tau-x', name: 'Hãng tàu X', category: 'Hãng tàu', standing: false },
    { id: 'nha-vuon-1', name: 'Nhà vườn 1', category: 'Chi hộ khách TQ', standing: false },
    { id: 'nha-vuon-2', name: 'Nhà vườn 2', category: 'Chi hộ khách TQ', standing: false },
    { id: 'dinh-ky-1', name: 'Nhà cung cấp định kỳ 1', category: 'Văn phòng', standing: true },
    { id: 'nguoi-nhan-1', name: 'Người nhận 1 (của Khách TQ 2)', category: 'Ứng tiền mặt', standing: false },
  ];

  const categories = ['Phí nâng hạ', 'Hãng tàu', 'Văn phòng', 'Chi hộ khách TQ', 'Ứng tiền mặt', 'Xe thuê', 'Phí ngân hàng'];

  // Phiếu thu đã có trong sổ nợ (R2, R5, R7). `reference` = mã ngân hàng đã ghi trên phiếu.
  const receipts = [
    { id: 'PT0101', customerId: 'kh-b', amount: 25000000n, date: '2026-11-23', reference: 'FT0001' },
    { id: 'PT0102', customerId: 'kh-c', amount: 40000000n, date: '2026-11-23', reference: null },
    { id: 'PT0103', customerId: 'kh-a', amount: 20000000n, date: '2026-11-23', reference: null },
    { id: 'PT0104', customerId: 'kh-b', amount: 30000000n, date: '2026-11-22', reference: null },
  ];

  // Hóa đơn còn mở (R4).
  const invoices = [{ id: 'HD0101', customerId: 'kh-c', amount: 35000000n }];

  // Tỷ giá: đồng cho 1 USD, số nguyên. Ngân hàng mua vào và tỷ giá tính cho khách (thỏa thuận).
  const rates = { bank: 25450n, customer: 25300n };

  // Từ đầu tháng tới hết hôm qua, theo danh mục: để thanh "Tháng này" có số nền, hôm nay cộng thêm.
  const monthBase = {
    thu: { 'Khách A': 380000000n, 'Khách B': 410000000n, 'Khách C': 290000000n },
    chi: { 'Phí nâng hạ': 64000000n, 'Hãng tàu': 520000000n, 'Văn phòng': 48000000n, 'Xe thuê': 130000000n, 'Phí ngân hàng': 2400000n },
  };

  // Sao kê sáng 24/11 (bước 1). Mỗi dòng: tài khoản, giờ, chiều, số tiền, người đối ứng, nội dung, mã ngân hàng.
  const t = (id, accountId, time, dir, amount, counterparty, content, bankRef = null) => ({ id, accountId, time: `${TODAY} ${time}`, dir, amount, currency: accountId === 'tk3' ? 'USD' : 'VND', counterparty, content, bankRef });
  const morningStatement = [
    t('g01', 'tk1', '07:41', 'in', 18000000n, 'Khách A', 'HTH0001K THANH TOAN CUOC'),
    t('g02', 'tk1', '07:44', 'in', 25000000n, 'Ngân hàng đối ứng 1', 'CK', 'FT0001'),
    t('g03', 'tk2', '07:46', 'in', 22000000n, 'Khách C', 'CK CUOC'),
    t('g04', 'tk2', '07:48', 'in', 35000000n, 'Người chuyển 1', 'TT HD0101'),
    t('g05', 'tk1', '07:50', 'in', 40000000n, 'Người chuyển 2', 'CK'),
    t('g06', 'tk1', '07:52', 'in', 19989000n, 'Người chuyển 3', 'CK'),
    t('g07', 'tk2', '07:55', 'in', 29700000n, 'Người chuyển 4', 'CK'),
    t('g08', 'tk2', '07:58', 'in', 12000000n, 'Bên thứ ba 1', 'THANH TOAN HO'),
    t('g09', 'tk2', '07:59', 'out', 3500000n, 'Đối tác mới 1', 'CHUYEN KHOAN'),
    t('g10', 'tk1', '08:00', 'out', 6000000n, 'Nhà cung cấp định kỳ 1', 'TIEN THUE VAN PHONG'),
    t('g11', 'tk1', '08:01', 'out', 50000000n, 'Công ty B', 'CK NOI BO'),
    t('g12', 'tk2', '08:01', 'in', 50000000n, 'Công ty A', 'CK NOI BO'),
    t('g13', 'tk4', '08:02', 'in', 2000000n, 'Người lạ 1', 'VIEC RIENG'),
    t('g14', 'tk4', '08:03', 'out', 1500000n, 'Người lạ 2', 'VIEC RIENG'),
  ];

  // Đề nghị chi nhân viên tạo (bước 3) và các dòng của các bước sau.
  const scenario = {
    request1: { code: 'DC0456', type: 'chi_thuong', amount: 8000000n, payeeId: 'cang-y', container: 'MAUU1000101', note: 'Phí nâng hạ container', attachment: 'hoa-don-gia-1.png', by: 'Nhân viên 1' },
    transfer1: t('g21', 'tk1', '10:42', 'out', 8000000n, 'Cảng Y', 'DC0456 PHI NANG HA'),
    expectation: { walletId: 'tq2', amount: 800000n, accountId: 'tk3', note: 'Khách TQ 2 báo chuyển trong ngày' },
    usdIn1: t('g31', 'tk3', '14:06', 'in', 1200000n, 'Công ty chuyển TQ 1', 'PAYMENT FOR GOODS'),
    usdSell: [
      t('g32', 'tk3', '14:20', 'out', 1200000n, 'Ngân hàng 1', 'BAN USD'),
      t('g33', 'tk1', '14:20', 'in', 305400000n, 'Ngân hàng 1', 'BAN USD'),
    ],
    usdIn2: t('g34', 'tk3', '14:40', 'in', 798500n, 'Công ty chuyển TQ 2', 'PAYMENT FOR GOODS'),
    request2: { code: 'DC0457', type: 'chi_ho', amount: 120000000n, payeeId: 'nha-vuon-1', walletId: 'tq1', note: 'Chi hộ Khách TQ 1 cho nhà vườn, 3 lệnh', attachment: 'bang-ke-gia-1.png', by: 'Nhân viên 1' },
    transfers2: [
      t('g41', 'tk1', '15:05', 'out', 50000000n, 'Nhà vườn 1', 'TT HANG LAN 1'),
      t('g42', 'tk1', '15:06', 'out', 40000000n, 'Nhà vườn 1', 'TT HANG LAN 2'),
      t('g43', 'tk1', '15:08', 'out', 30000000n, 'Nhà vườn 1', 'TT HANG LAN 3'),
    ],
    noRequest: t('g51', 'tk2', '15:20', 'out', 5500000n, 'Nhà vườn 2', 'UNG TIEN'),
    request3: { code: 'DC0458', type: 'ung_tien_mat', amount: 30000000n, payeeId: 'nguoi-nhan-1', walletId: 'tq2', note: 'Ứng tiền mặt cho người của Khách TQ 2', attachment: 'de-nghi-gia-1.png', by: 'Nhân viên 1' },
    cashOut: t('g61', 'quy', '16:20', 'out', 30000000n, 'Người nhận 1 (của Khách TQ 2)', 'GIAO TIEN MAT DC0458'),
  };

  return { TODAY, companies, accounts, ownNames, customers, wallets, payers, unknownPayers, payees, categories, receipts, invoices, rates, monthBase,
    morningStatement, scenario };
})();
if (typeof module !== 'undefined') module.exports = ThuChiTuSinhFixture;
