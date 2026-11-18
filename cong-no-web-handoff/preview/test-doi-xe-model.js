const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('./doi-xe-model.js');

// CHI-PHI-XE-01: dữ liệu giả cùng dạng GET /api/v7/doixe/so. Biển số, tên, container đều bịa.
const PHI = [['nang', 'Phí nâng', 12], ['nangha', 'Nâng hạ', 13], ['cau', 'Cầu đường', 14], ['neo', 'Neo', 15], ['xi', 'Xí cont', 16],
  ['dao', 'Đảo cont', 17], ['moi', 'Cont mới', 18], ['doi', 'Dời cont', 19], ['seal', 'Mua seal', 20], ['bai', 'Bãi chờ', 21],
  ['dieu', 'Điều độ', 22], ['dau', 'Đổ dầu', 23], ['ps', 'Phát sinh', 24], ['may', 'Nổ máy', 27], ['vetc', 'VETC', 26]]
  .map(([ma, ten, cot], i) => ({ ma, ten, ten_day_du: null, thu_tu: i + 1, cot_sheet: cot, cong_ty_tra: ma === 'vetc' }));
const XE = [{ id: 1, bien_so: '99Z-900.01', tai_xe_id: 11, dang_dung: true }, { id: 2, bien_so: '99Z-900.02', tai_xe_id: 12, dang_dung: true },
  { id: 3, bien_so: '99Y-800.01', tai_xe_id: null, dang_dung: true }];
const CTX = { loai: 'tai_xe', nguoiId: 11, xe: 1, homNay: '2026-11-18' };
const sheetRow = (o = {}) => {
  const c = Array(29).fill('');
  c[2] = o.ngay ?? ''; c[3] = o.cont ?? ''; c[8] = o.xe ?? ''; c[25] = o.gc ?? ''; c[26] = o.vetc ?? ''; c[28] = o.tong ?? '';
  for (const [ma, v] of Object.entries(o.phi ?? {})) c[PHI.find(p => p.ma === ma).cot_sheet] = v;
  return c.join('\t');
};
const chang = (id, o = {}) => ({ id, ngay: '2026-11-05', container: `MAUU000000${id}`, loai: 'hang', xe_id: 1, tai_xe_id: 11, tra: 'nguoi',
  nguoi_tra_id: 11, da_bo: false, sau_khoa: false, chuyen: null, dong: [{ id: id * 10, loai: 'goc', dot_hoan_id: null, phi: {} }], ...o });

test('đọc tiền: trống là null, nhóm nghìn chấm/phẩy là số, lẻ/âm/chữ là lỗi', () => {
  assert.deepEqual(M.docTien(''), { v: null });
  assert.deepEqual(M.docTien(' - '), { v: null });
  assert.deepEqual(M.docTien('300,000'), { v: 300000 });
  assert.deepEqual(M.docTien('1.250.000 đ'), { v: 1250000 });
  assert.deepEqual(M.docTien('0'), { v: 0 });
  assert.equal(M.docTien('157500.5').loi, 'Số lẻ');
  assert.equal(M.docTien('3,5').loi, 'Số lẻ');
  assert.equal(M.docTien('-200').loi, 'Số âm');
  assert.equal(M.docTien('abc').loi, 'Không phải số');
  assert.equal(M.fmt(-1250000), '−1.250.000');
  assert.equal(M.fmtDau(100000), '+100.000');
  assert.equal(M.docSo(3500000), '3 triệu 500 nghìn');
});

test('ngày: Sheet ghi tháng/ngày/năm (số đầu > 12 là ngày/tháng), gõ tay là ngày/tháng của năm hôm nay', () => {
  assert.deepEqual(M.docNgaySheet('10/2/2026'), { v: '2026-10-02' });
  assert.deepEqual(M.docNgaySheet('17/11/2026'), { v: '2026-11-17' });
  assert.deepEqual(M.docNgaySheet('2/30/2026'), { loi: 'Ngày lạ' });
  assert.deepEqual(M.docNgayGo('05/11', '2026-11-18'), { v: '2026-11-05' });
  assert.deepEqual(M.docNgayGo('5-11-26', '2026-11-18'), { v: '2026-11-05' });
  assert.equal(M.docNgayGo('32/1', '2026-11-18').loi, 'Ngày lạ');
});

test('dán khối 29 cột: tiêu đề và dòng trống bỏ, loại đoán từ ghi chú, ô lỗi giữ chữ, cột tổng chỉ cảnh báo, dán lại không trùng', () => {
  const head = ['STT', 'TRÂN/GL', 'NGÀY', 'SỐ CONT'].concat(Array(25).fill('x')).join('\t');
  const text = [head,
    sheetRow({ ngay: '11/17/2026', cont: 'mauu 1234567', phi: { nang: '450,000', nangha: '350,000' }, vetc: '240,000', tong: '800,000' }),
    sheetRow({ ngay: '11/17/2026', cont: 'MAUU1234567', phi: { nangha: '250,000' }, gc: 'trả rỗng về bãi', tong: '250,000' }),
    sheetRow({ ngay: '11/19/2026', cont: 'MAUU2222222', phi: { nangha: '300,000' } }),
    sheetRow({ ngay: '11/16/2026', cont: 'MAUU3333333', phi: { ps: '157500.5' } }),
    sheetRow({ phi: { nangha: '300,000' } }),
    sheetRow({ ngay: '11/15/2026', cont: 'MAUU4444444', xe: '90002', phi: { nangha: '300,000', may: '100,000' }, tong: '300,000' }),
    sheetRow({ ngay: '11/15/2026', cont: 'MAUU5555555', xe: '12', phi: { nangha: '300,000' } }),
    sheetRow({}), ''].join('\n');
  const kq = M.danKhoi(text, CTX, PHI, XE, new Set(), []);
  assert.equal(kq.drafts.length, 7);
  assert.match(kq.cau, /^Vừa dán 8 dòng: 7 dòng nháp, 4 dòng có ô đỏ cần sửa · bỏ 1 dòng trống$/);
  const [a, b, c, d, e, f, g] = kq.drafts;
  assert.deepEqual([a.ngay, a.container, a.loai, a.xe, a.phi], ['2026-11-17', 'MAUU1234567', 'hang', 1, { nang: 450000, nangha: 350000, vetc: 240000 }]);
  assert.equal(b.loai, 'tra_rong');
  assert.equal(M.kiemDong(a, new Set(), kq.drafts, PHI, '2026-11-18').canhBao, '', 'tổng Sheet bằng tài xế chi, VETC không vào');
  assert.equal(M.kiemDong(c, new Set(), kq.drafts, PHI, '2026-11-18').loiCot.ngay, 'Ngày sau hôm nay');
  assert.deepEqual([d.loiO.ps, d.tho.ps], ['Số lẻ', '157500.5']);
  assert.equal(M.kiemDong(e, new Set(), kq.drafts, PHI, '2026-11-18').loi, 'Có tiền, thiếu ngày và cont');
  assert.equal(f.xe, 2, 'số xe khớp chữ số cuối của biển');
  assert.equal(M.kiemDong(f, new Set(), kq.drafts, PHI, '2026-11-18').canhBao, 'Sheet ghi tổng 300.000', 'nổ máy vào tài xế chi nên khác tổng Sheet');
  assert.equal(g.xeLoi, 'Không rõ xe');
  const lai = M.danKhoi(text, CTX, PHI, XE, new Set(), kq.drafts);
  assert.equal(lai.drafts.length, 0);
  assert.match(lai.cau, /bỏ 7 dòng đã có/);
  const daLuu = new Set([M.khoaChang(a)]);
  assert.equal(M.danKhoi(text, CTX, PHI, XE, daLuu, []).drafts.length, 6, 'chặng đã lưu không thành nháp');
  const ngan = M.danKhoi(['11/17/2026', 'MAUU9999999', '', 'Đắk Lắk', 'KHO', 'TX', '', 'A', 'B', 'SR'].concat(Array(13).fill(''), [''], [''], ['']).join('\t').replace(/^/, ''), CTX, PHI, XE, new Set(), []);
  assert.equal(ngan.drafts[0].container, 'MAUU9999999', 'khối bắt đầu từ cột NGÀY');
});

test('ngữ cảnh sổ: tài xế trả ở sổ tài xế; người đi lệnh trả, tài xế theo xe; sổ xe tài xế của xe trả; xe thuê không có tài xế', () => {
  const draft = xe => M.nhapTuGo({ ngay: '17/11', container: 'MAUU1', loai: 'hang', xe, phi: { nangha: '300' } }, ctx, PHI, XE, '2026-11-18');
  let ctx = CTX;
  assert.deepEqual([draft('').taiXe, draft('').nguoiTra, draft('').xe], [11, 11, 1]);
  ctx = { loai: 'di_lenh', nguoiId: 31, xe: null, homNay: '2026-11-18' };
  assert.deepEqual([draft('2').taiXe, draft('2').nguoiTra], [12, 31]);
  assert.deepEqual([draft('3').taiXe, draft('3').nguoiTra], [null, 31]);
  assert.equal(M.kiemDong(draft(''), new Set(), [], PHI, '2026-11-18').loiCot.xe, 'Chưa chọn xe');
  ctx = { loai: 'xe', nguoiId: null, xe: 3, homNay: '2026-11-18' };
  const rented = draft('');
  assert.deepEqual([rented.taiXe, rented.nguoiTra, M.dongGui(rented).tra], [null, null, 'cong_ty']);
  const sent = M.dongGui(M.nhapTuGo({ ngay: '17/11', container: ' mauu 1 ', loai: 'hang', xe: '', ghi_chu: ' vá vỏ ', phi: { nangha: '300', vetc: '' } }, CTX, PHI, XE, '2026-11-18'));
  assert.deepEqual(sent, { ngay: '2026-11-17', container: 'MAUU1', loai: 'hang', xe_id: 1, tai_xe_id: 11, tra: 'nguoi', nguoi_tra_id: 11,
    noi_lay: null, noi_ha: null, kho: null, tinh: null, ten_hang: null, ghi_chu: 'vá vỏ', phi: { nangha: '300' } });
});

test('tiền chặng: dòng gốc + điều chỉnh + trừ lại; VETC không vào phần hoàn; hiệu lực theo phí; trống là null', () => {
  const c = chang(1, { dong: [
    { id: 10, loai: 'goc', dot_hoan_id: 5, phi: { nang: '450', nangha: '350', vetc: '120' } },
    { id: 11, loai: 'dieu_chinh', dot_hoan_id: null, phi: { nang: '-50' } },
    { id: 12, loai: 'dieu_chinh', dot_hoan_id: null, phi: { neo: '100' } }] });
  assert.equal(M.tienDong(c.dong[0], PHI), 800);
  assert.equal(M.tienChang(c, PHI), 850);
  assert.equal(M.phiHieuLuc(c, 'nang'), 400);
  assert.equal(M.phiHieuLuc(c, 'cau'), null);
  assert.equal(M.tienChang(chang(2), PHI), null);
  assert.equal(M.coPhi(chang(2)), false);
  assert.equal(M.coPhi(chang(3, { dong: [{ id: 30, loai: 'goc', dot_hoan_id: null, phi: { vetc: '90' } }] })), true, 'chỉ có VETC vẫn là có phí');
  const cho = M.dongChuaHoan([c, chang(4, { nguoi_tra_id: 31, dong: [{ id: 40, loai: 'goc', dot_hoan_id: null, phi: { nang: '1' } }] })], 11, PHI);
  assert.deepEqual(cho.map(x => [x.dong.id, x.tien]), [[11, -50], [12, 100]]);
  assert.equal(M.tongChon(cho, new Set([11, 12])), 50);
  assert.equal(M.laChuaHoan(c, 11, PHI), true);
});

test('số dư bằng chữ, thẻ tiền, đợt hoàn khác tổng, thứ tự bảng người', () => {
  assert.equal(M.loiDu(1200000, 'A'), 'Công ty còn nợ 1.200.000');
  assert.equal(M.loiDu(-300000, 'A'), 'A đang giữ 300.000');
  assert.equal(M.nhanCuoi(-1, 'A'), 'A đang giữ tiền ứng');
  assert.equal(M.cuoiThe({ dau_vnd: '1000', chi_vnd: '500', hoan_vnd: '200', ung_vnd: '300' }), 1000);
  assert.equal(M.chenhDot({ tong_dong_vnd: '1550', so_tien_vnd: '1150' }), 400);
  assert.equal(M.truUngGiu(-500), 0);
  assert.equal(M.sauKhiGhi(900, 1150), -250);
  const rows = [{ id: 1, so_du_vnd: '-300', chua_hoan: 1 }, { id: 2, so_du_vnd: '500', chua_hoan: 2 }, { id: 3, so_du_vnd: '900', chua_hoan: 0 },
    { id: 4, so_du_vnd: '0', chua_hoan: 0 }, { id: 5, so_du_vnd: '-800', chua_hoan: 0 }];
  assert.deepEqual(M.xepNguoi(rows).map(r => r.id), [3, 2, 5, 1, 4]);
  assert.deepEqual(M.tongNguoi(rows), { no: 1400, giu: 1100, chuaHoan: 3 });
  assert.throws(() => M.so('1.5'));
});

test('cách xem Gọn: 5 phí dùng nhiều nhất (bằng nhau thì theo thứ tự cột Sheet), còn lại vào Phí khác; tổng cột theo người trả', () => {
  const ds = [chang(1, { dong: [{ id: 10, loai: 'goc', dot_hoan_id: null, phi: { neo: '1', ps: '2', may: '3', dau: '4', cau: '5', seal: '6' } }] }),
    chang(2, { nguoi_tra_id: 31, dong: [{ id: 20, loai: 'goc', dot_hoan_id: null, phi: { neo: '10', ps: '20', vetc: '7' } }] })];
  const g = M.cotPhiGon(ds, PHI, 5);
  assert.deepEqual(g.hien.map(p => p.ma), ['cau', 'neo', 'seal', 'dau', 'ps']);
  assert.deepEqual(g.khac.map(p => p.ma), ['may']);
  assert.equal(M.phiKhac(ds[0], g.khac).tong, 3);
  assert.deepEqual(M.cotPhiGon([chang(9)], PHI, 5).hien.map(p => p.ma), ['nang', 'nangha'], 'tháng chưa có phí vẫn có Phí nâng, Nâng hạ để gõ');
  assert.equal(M.tongCot(ds, 'neo', 11, false), 1, 'dòng người khác trả không cộng');
  assert.equal(M.tongCot(ds, 'vetc', 11, false), 7, 'VETC cộng mọi dòng');
  assert.equal(M.tongCot(ds, 'neo', null, true), 11, 'sổ xe cộng mọi dòng');
  assert.equal(M.tongChi(ds, PHI, 11, false), 21);
  assert.deepEqual(M.theXe(ds, PHI, [{ id: 11, vai: 'tai_xe' }, { id: 31, vai: 'di_lenh' }]), { soChang: 2, hang: 2, phu: 0, tx: 21, dl: 30, cty: 0, vetc: 7, tong: 58 });
});

test('Lịch sử viết thành câu: trước → sau, lý do, khóa tháng', () => {
  const dm = { nguoi: [{ id: 11, ten: 'Tài xế giả' }], xe: [{ id: 1, bien_so: '99Z-900.01' }] };
  const t = M.moTaSuKien({ viec: 'huy_ung', nguoi_id: 11, truoc: { ngay: '2026-11-08', so_tien_vnd: '3000000', so_du_vnd: '-500' }, sau: { so_du_vnd: '2500' }, ly_do: 'ghi trùng' }, dm, PHI);
  assert.deepEqual(t, { viec: 'Hủy lần ứng', chi: '08/11 · 3.000.000', truoc: 'Tài xế giả đang giữ 500', sau: 'Công ty còn nợ 2.500', lyDo: 'ghi trùng' });
  const d = M.moTaSuKien({ viec: 'dieu_chinh', nguoi_id: 11, truoc: { cot: 'phi:neo', gia_tri: null, ngay: '2026-10-05', container: 'MAUU1' }, sau: { gia_tri: '100000', chenh_vnd: '100000', ly_do_dc: 'thang_khoa' } }, dm, PHI);
  assert.deepEqual([d.viec, d.chi, d.truoc, d.sau], ['Điều chỉnh', 'Tháng đã khóa · Neo · 05/10 · MAUU1', '—', '100.000 (thêm dòng +100.000)']);
  assert.equal(M.moTaSuKien({ viec: 'khoa_thang', truoc: { thang: '2026-10-01', khoa: false }, sau: { thang: '2026-10-01', khoa: true } }, dm, PHI).viec, 'Khóa tháng 10/2026');
  assert.equal(M.moTaSuKien({ viec: 'sua_chang', nguoi_id: 11, truoc: { cot: 'xe_id', gia_tri: '1', ngay: '2026-11-01', container: 'C' }, sau: { gia_tri: '9' } }, dm, PHI).truoc, '99Z-900.01');
});

test('thanh tháng: sổ mới vẫn có tháng trước; tháng đang xem luôn có; tối đa 6 tháng', () => {
  assert.deepEqual(M.cacThang(['2026-11-01'], '2026-11-18', '2026-11-01'), ['2026-10-01', '2026-11-01']);
  assert.deepEqual(M.cacThang([], '2027-01-05', null), ['2026-12-01', '2027-01-01']);
  const nhieu = ['2026-03-01', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01', '2026-09-01'];
  assert.deepEqual(M.cacThang(nhieu, '2026-11-18', '2026-03-01')[0], '2026-03-01');
  assert.equal(M.cacThang(nhieu, '2026-11-18', '2026-11-01').length, 6);
});
