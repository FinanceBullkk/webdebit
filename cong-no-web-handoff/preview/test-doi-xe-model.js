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
    noi_lay: null, noi_ha: null, kho: null, tinh: null, ten_hang: null, ghi_chu: 'vá vỏ', phi: { nangha: '300' },
    neo_ngay: null, may_gio: null, km: null });
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
  // DX-05: ứng, đợt hoàn và hủy khi tháng đã khóa có nhãn trong Lịch sử; khoản cũ (không có cờ) như trước.
  assert.match(M.moTaSuKien({ viec: 'ghi_ung', nguoi_id: 11, truoc: { so_du_vnd: '0' }, sau: { ngay: '2026-10-20', so_tien_vnd: '200000', so_du_vnd: '-200000', sau_khoa: true } }, dm, PHI).chi, / · sau khóa \(tháng đã khóa\)$/);
  assert.match(M.moTaSuKien({ viec: 'huy_hoan', nguoi_id: 11, truoc: { ngay: '2026-10-20', so_tien_vnd: '1' }, sau: { dong_tro_lai: 2, sau_khoa: true } }, dm, PHI).chi, /Chưa hoàn · sau khóa/);
  assert.doesNotMatch(M.moTaSuKien({ viec: 'ghi_hoan', nguoi_id: 11, truoc: {}, sau: { so_dong: 1, tong_dong_vnd: '1', so_tien_vnd: '1', ngay: '2026-11-01' } }, dm, PHI).chi, /sau khóa/);
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

test('phiếu chi mới: số lượng (ngày neo, giờ máy, km) không phải tiền; Nổ máy ghi giờ thành số giờ; km đọc từ ô Tỉnh', () => {
  const phi = PHI.concat({ ma: 'hasom', ten: 'Hạ sớm/KH', ten_day_du: 'Hạ sớm · kiểm hoá', thu_tu: 16, cot_sheet: null, cong_ty_tra: false });
  assert.deepEqual(M.docSoLuong('', 365), { v: null });
  assert.deepEqual(M.docSoLuong('2 ngày', 365), { v: 2 });
  assert.deepEqual(M.docSoLuong('5 TIẾNG', 999), { v: 5 });
  assert.deepEqual(M.docSoLuong('120km', 9999), { v: 120 });
  assert.equal(M.docSoLuong('1,5', 999).loi, 'Số lẻ');
  assert.equal(M.docSoLuong('0', 999).loi, 'Số 0: để trống');
  assert.equal(M.docSoLuong('366', 365).loi, 'Quá 365');
  assert.equal(M.docSoLuong('abc', 365).loi, 'Không phải số');
  const row = (may, tinh) => { const c = Array(29).fill(''); c[2] = '11/17/2026'; c[3] = 'MAUU1111111'; c[5] = tinh; c[13] = '300,000'; c[27] = may; return c.join('\t'); };
  const [gio, tien, chu] = M.danKhoi([row('5H', 'Long An, 45 km'), row('200,000', 'Bình Dương'), row('3 TIẾNG', '')].join('\n')
    .replace(/MAUU1111111/g, (m, i) => `MAUU111111${i % 10}`), CTX, phi, XE, new Set(), []).drafts;
  assert.deepEqual([gio.may_gio, gio.phi.may, gio.km, gio.loiO.may], [5, undefined, 45, undefined], '5H là giờ máy, không phải tiền');
  assert.deepEqual([tien.may_gio, tien.phi.may, tien.km], [null, 200000, null], 'số không đơn vị vẫn là tiền như cũ');
  assert.equal(chu.may_gio, 3);
  assert.equal(M.chiNhap(gio, phi), 300000, 'giờ máy không cộng vào tài xế chi');
  const moi = M.nhapTuGo({ ngay: '17/11', container: 'MAUU2222222', loai: 'hang', xe: '1', neo_ngay: '2', may_gio: '1,5', km: '',
    phi: { hasom: '250.000' } }, CTX, phi, XE, '2026-11-18');
  assert.deepEqual([moi.neo_ngay, moi.loiSL.may_gio, moi.thoSL.may_gio, moi.phi.hasom], [2, 'Số lẻ', '1,5', 250000]);
  assert.equal(M.kiemDong(moi, new Set(), [moi], phi, '2026-11-18').loi, 'Số lẻ');
  M.ganSoLuong(moi, 'may_gio', '4', 999);
  assert.equal(M.kiemDong(moi, new Set(), [moi], phi, '2026-11-18').loi, '');
  const gui = M.dongGui(moi);
  assert.deepEqual([gui.neo_ngay, gui.may_gio, gui.km, gui.phi.hasom], ['2', '4', null, '250000']);
  assert.equal(M.chiNhap(moi, phi), 250000, 'Hạ sớm/KH là tài xế chi');
  assert.ok(M.moiCo({ km: '12' }), 'hàng trống chỉ gõ km vẫn là có chữ');
  assert.equal(M.moTaSuKien({ viec: 'sua_chang', truoc: { cot: 'may_gio', gia_tri: null, ngay: '2026-11-17', container: 'MAUU1' },
    sau: { gia_tri: '4' } }, { nguoi: [], xe: [] }, phi).chi, 'Giờ máy · 17/11 · MAUU1');
});

test('ngày áp giá (audit DX-01): thiếu năm thì lấy năm gần nhất không trước tháng này, quanh tháng 12 và tháng 1; đủ năm thì giữ, báo áp ngược', () => {
  // Tháng 12: "01/01" là 01/01 năm sau, không phải 01/01 năm nay (lỗi cũ áp giá ngược cả năm).
  assert.deepEqual(M.docNgayApGia('01/01', '2026-12-05'), { v: '2027-01-01', cu: false });
  assert.deepEqual(M.docNgayApGia('1.1', '2026-12-31'), { v: '2027-01-01', cu: false });
  assert.deepEqual(M.docNgayApGia('01/12', '2026-12-05'), { v: '2026-12-01', cu: false }, 'mùng 1 tháng này vẫn là tháng này');
  assert.deepEqual(M.docNgayApGia('20/11', '2026-12-05'), { v: '2026-11-20', cu: true }, 'tháng trước: ngày gần nhất, áp ngược nên hỏi');
  // Tháng 1: "28/12" thiếu năm là 28/12 năm nay (tương lai); muốn áp ngược về tháng 12 năm trước thì gõ đủ năm.
  assert.deepEqual(M.docNgayApGia('28/12', '2027-01-10'), { v: '2026-12-28', cu: true });
  assert.deepEqual(M.docNgayApGia('28/12/2026', '2027-01-10'), { v: '2026-12-28', cu: true });
  assert.deepEqual(M.docNgayApGia('01/02', '2027-01-10'), { v: '2027-02-01', cu: false });
  assert.deepEqual(M.docNgayApGia('01/01/26', '2026-12-05'), { v: '2026-01-01', cu: true }, 'năm hai chữ số');
  assert.deepEqual(M.docNgayApGia('29/02', '2026-12-05'), { loi: 'Ngày lạ' }, '2027 không nhuận');
  assert.deepEqual(M.docNgayApGia('', '2026-12-05'), { v: null });
  assert.equal(M.docNgayApGia('1/13', '2026-12-05').loi, 'Ngày lạ');
  // Ô mặc định có đủ năm: mùng 1 tháng sau.
  assert.equal(M.ngayApMacDinh('2026-12-05'), '01/01/2027');
  assert.equal(M.ngayApMacDinh('2026-11-18'), '01/12/2026');
  assert.equal(M.ngayApMacDinh('2027-01-31'), '01/02/2027');
  assert.deepEqual(M.docNgayApGia(M.ngayApMacDinh('2026-12-05'), '2026-12-05'), { v: '2027-01-01', cu: false });
});

test('khoản trùng và tổng phí chặng (audit DX-03, DX-06): bỏ khoản đã hủy; tổng gồm cả dòng điều chỉnh và phí công ty trả', () => {
  const ds = [{ id: 1, ngay: '2026-11-05', so_tien_vnd: '3000000', huy: null, actor: 'a' },
    { id: 2, ngay: '2026-11-06', so_tien_vnd: '3000000', huy: { ly_do: 'x' } }];
  assert.equal(M.khoanTrung(ds, '2026-11-05', 3000000).id, 1);
  assert.equal(M.khoanTrung(ds, '2026-11-06', 3000000), null, 'khoản đã hủy không tính');
  assert.equal(M.khoanTrung(ds, '2026-11-05', 2000000), null);
  assert.equal(M.khoanTrung(undefined, '2026-11-05', 1), null);
  assert.equal(M.tongPhiChang(chang(1, { dong: [{ id: 1, loai: 'goc', phi: { nang: '450000', vetc: '120000' } },
    { id: 2, loai: 'dieu_chinh', phi: { nang: '-50000' } }] })), 520000);
  assert.equal(M.tongPhiChang(chang(2)), 0, 'chặng chưa có ô phí nào: 0 (máy chủ cũng so 0)');
});
