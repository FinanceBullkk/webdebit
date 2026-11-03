// Dữ liệu giả chép từ HTML handoff; không đọc khách/Sheet/DB thật.
module.exports = world => {
  const month = '2026-11-01';
  world.month = '2026-11'; world.todayMonth = month; world.legacy = [];
  world.customers = [{ id: 1, name: 'Công ty Mẫu An Phát', commodity: 'Sầu riêng', transport_mode: 'CANG', status: 'active' }];
  world.locks = [{ month, locked: false }];
  world.feeTypes.push({ id: 10, name: 'Nâng hạ', kind: 'service', sign: 'positive', active: true, sort: 10 });
  world.feeColumns = [10];
  const rows = [
    ['MSKU7712045','Maersk','Shipper A','01','Krông Pắc','Cát Lái','9200000','350000',null,'9550000'],
    ['MSKU7712051','Maersk','Shipper A','01','Krông Pắc','Cát Lái','9200000','350000',null,'9550000'],
    ['ONEU4418820','ONE','Shipper B','01','Buôn Hồ','Cát Lái','9500000','350000','200000','10050000'],
    ['ONEU4418836','ONE','Shipper B','01','Buôn Hồ','Cát Lái','9500000','350000',null,'9850000'],
    ['CMAU6620117','CMA CGM','Shipper A','02','Krông Pắc','Hiệp Phước','9800000',null,null,'9800000'],
    ['CMAU6620123','CMA CGM','Shipper A','02','Krông Pắc','Hiệp Phước','9800000',null,'150000','9950000'],
    ['TGHU8801274','Maersk','Shipper C','02','Ea Kar','Cát Lái',null,null,null,null],
    ['TGHU8801280','Maersk','Shipper C','02','Ea Kar','Cát Lái',null,null,null,null],
  ];
  world.trips = rows.map(([container, carrier, shipper, day, origin, destination, unit_price_vnd, lift, other, amount_vnd], index) => ({
    id: index + 11, month, container, carrier, shipper, event_date: `2026-11-${day}`, origin, destination,
    unit_price_vnd, other_fee_vnd: other, amount_vnd, status: 'confirmed', is_missing_price: unit_price_vnd == null,
    editable: true, info_editable: true, deleted: false,
    fee_lines: [...(lift ? [{ id: 100 + index, fee_type_id: 10, amount_vnd: lift }] : []), ...(other ? [{ id: 200 + index, fee_type_id: 7, amount_vnd: other }] : [])],
  }));
  world.months = ['07','08','09','10','11'].map(m => ({ month: `2026-${m}-01`, prior_months_vnd: m === '11' ? '412600000' : '0',
    charges_vnd: m === '11' ? '58750000' : '0', received_vnd: m === '11' ? '150000000' : '0', end_of_month_vnd: m === '11' ? '321350000' : '0' }));
  world.total = '321350000';
  world.receipts = [['01','Chuyển khoản','UNC 0111 · Vietcombank','100000000'], ['02','Tiền mặt','Anh Tâm nộp tại văn phòng','50000000']].map(([day, method, reference, amount_vnd], index) => ({
    id: index + 1, pid: `PH-00${index + 1}`, date: `2026-11-${day}`, method, reference, amount_vnd, voided_by_event: null,
    allocations: [{ month: '2026-08-01', amount_vnd, superseded_by_event: null }],
  }));
};
