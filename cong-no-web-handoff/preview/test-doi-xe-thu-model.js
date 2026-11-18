// DOI-XE-THU-01: phép tính và kiểm ô của màn Bảng kê gửi HTH + Bảng giá (doi-xe-thu-model.js). Dữ liệu giả.
const assert = require('node:assert/strict');
const test = require('node:test');
const T = require('./doi-xe-thu-model.js');

const line = o => ({ chang_id: 1, ngay: '2026-11-03', container: 'MAUU1000001', loai: 'hang', ten_hang: 'Hàng giả', tinh: 'Tỉnh giả',
  tuyen: 'Hàng giả · Tỉnh giả', gia_bang_vnd: '1000000', cuoc_vnd: '1000000', cuoc_tay: false, ghep_vnd: null, ps_vnd: null, chi_ho_vnd: null,
  ps: [], chua_doc: 0, khoan_la: 0, chang_con: true, ...o });
const tong = { cuoc_vnd: '3000000', ghep_vnd: '500000', ps_vnd: '700000', chi_ho_vnd: '200000', dc_vnd: '-100000', doi_vnd: '4100000',
  tra_vnd: '1000000', con_vnd: '3100000', so_chang: 3, chua_gia: 1, khac_gia: 1, chua_doc: 1, khoan_la: 0 };

test('trạng thái bảng kê theo bước: đang gom → đang đối chiếu → chờ HTH trả → thu đủ', () => {
  assert.equal(T.trangThai({ bang_ke: null }), 'nhap');
  assert.equal(T.trangThai({ bang_ke: { trang_thai: 'da_gui' } }), 'gui');
  assert.equal(T.trangThai({ bang_ke: { trang_thai: 'da_doi_chieu', thu_du: false } }), 'doi');
  assert.equal(T.trangThai({ bang_ke: { trang_thai: 'da_doi_chieu', thu_du: true } }), 'du');
  assert.deepEqual(Object.values(T.NUT), ['Gửi bảng kê', 'Đối chiếu xong', 'Ghi tiền HTH trả', '']);
  assert.equal(T.nhanTrangThai({ bang_ke: { trang_thai: 'da_gui', gui_ngay: '2026-11-03' } }), 'Đã gửi 03/11 · đang đối chiếu');
  assert.equal(T.nhanTrangThai({ bang_ke: { trang_thai: 'da_doi_chieu', thu_du: true }, tien_ve: [{ ngay: '2026-11-12', huy: null }] }), 'HTH trả đủ 12/11');
});

test('thanh tháng: tháng chưa thu đủ luôn hiện, thêm bốn tháng gần nhất', () => {
  const ds = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10', '2026-11'].map((m, i) => ({ thang: `${m}-01`, trang_thai: i === 0 ? 'doi' : i < 6 ? 'du' : 'nhap' }));
  assert.deepEqual(T.cacThang(ds, '2026-11-01').map(x => x.thang), ['2026-05-01', '2026-08-01', '2026-09-01', '2026-10-01', '2026-11-01']);
});

test('tổng dòng như file debit; ô trống không thành 0; cờ và bộ lọc', () => {
  assert.equal(T.tongDong(line({ ghep_vnd: '300000', ps_vnd: '200000' })), 1500000);
  assert.equal(T.tongDong(line({ cuoc_vnd: null })), null);
  const dong = [line(), line({ cuoc_vnd: null, tuyen: null, gia_bang_vnd: null }), line({ cuoc_tay: true, cuoc_vnd: '900000' }),
    line({ chua_doc: 1 }), line({ loai: 'rut_mooc' }), line({ dc_vnd: '-100000' })];
  assert.deepEqual(T.locChips(dong, 'all').map(x => `${x.k}:${x.n}`), ['all:6', 'chuagia:1', 'khacgia:1', 'chuadoc:1', 'dc:1', 'phu:1']);
  assert.deepEqual(T.viecTruocGui(dong).map(x => x.text), ['1 chặng chưa có giá', '1 chặng giá khác bảng giá', '1 ghi chú phát sinh chưa đọc được']);
  assert.equal(T.coCau(tong), 'Cước 3.000.000 · Đóng ghép 500.000 · Phát sinh 500.000 · Chi hộ 200.000 · Điều chỉnh −100.000 · 3 chặng');
  assert.equal(T.tenTuyen(line({ tuyen: null, ten_hang: 'Sầu đông', tinh: null })), 'Sầu đông');
  assert.equal(T.tenTuyen(line({ tuyen: null, ten_hang: null, tinh: null, loai: 'chuyen_cang' })), 'Chuyển cảng');
});

test('chi tiết dòng: giá bảng 70% cho mooc, giá tay khác bảng, khoản phát sinh, chi hộ, chưa đọc', () => {
  const text = T.chiTiet(line({ loai: 'rut_mooc', gia_bang_vnd: '700000', cuoc_tay: true, cuoc_vnd: '800000',
    ps: [{ goc: 'Kiểm hoá 150k', ten: 'Kiểm hoá', so_tien_vnd: '150000', chi_ho: true }, { goc: 'Cân', loi: 'Thiếu số tiền (ví dụ 200k)' }] })).map(x => x.text);
  assert.match(text[0], /700\.000 \(70% giá tuyến vì là rút mooc\)/);
  assert.match(text[1], /nhập tay 800\.000, khác bảng giá \+100\.000/);
  assert.equal(text[2], 'Kiểm hoá: 150.000 · chi hộ');
  assert.match(text[3], /chưa đọc được: «Cân»/);
});

test('điều chỉnh: bớt/thêm, Đòi HTH và dòng trước → sau, lý do bắt buộc, không để dòng âm', () => {
  const d = line({ ps_vnd: '200000', dc_vnd: '-50000' });
  const x = T.dcXem(tong, d, 'bot', '380.000', 'HTH báo trùng');
  assert.equal(x.v, -380000);
  assert.equal(x.xem, 'Đòi HTH: 4.100.000 → 3.720.000 · dòng này 1.150.000 → 770.000');
  assert.equal(x.loi, '');
  assert.equal(T.dcXem(tong, d, 'them', '100000', ' ').loi, 'Ghi lý do: HTH thắc mắc gì, ai báo.');
  assert.match(T.dcXem(tong, d, 'bot', '2.000.000', 'x').loi, /Bớt nhiều hơn tổng dòng/);
  assert.match(T.dcXem(tong, d, 'bot', '1,5', 'x').loi, /Số tiền/);
  assert.equal(T.dcXem(tong, d, 'bot', '', 'x').v, null);
});

test('tiền về: không trước ngày gửi, không sau hôm nay, thừa chặn, thiếu cảnh báo', () => {
  const data = { thang: '2026-10-01', hom_nay: '2026-11-18', tong, bang_ke: { gui_ngay: '2026-11-03' } };
  assert.match(T.tvXem(data, '19/11', '1000').loi, /sau hôm nay/);
  assert.match(T.tvXem(data, '02/11', '1000').loi, /trước ngày gửi bảng kê \(03\/11\)/);
  assert.match(T.tvXem(data, '18/11', '3.100.001').loi, /Lớn hơn số còn phải thu \(3\.100\.000\)/);
  const thieu = T.tvXem(data, '18/11', '3.000.000');
  assert.equal(thieu.loi, '');
  assert.equal(thieu.ngay, '2026-11-18');
  assert.equal(thieu.xem, 'Còn phải thu: 3.100.000 → 100.000');
  assert.equal(thieu.canh, 'Trả thiếu 100.000: tháng 10/2026 vẫn chờ phần còn lại.');
  assert.equal(T.tvXem(data, '18/11', '3100000').canh, '');
  assert.equal(T.huyXem(100000, { so_tien_vnd: '3000000' }), 'Còn phải thu: 100.000 → 3.100.000');
});

test('gửi: tóm tắt và cảnh báo chặng chưa có giá, tháng chưa hết', () => {
  const x = T.guiXem({ tong, thang: '2026-11-01', hom_nay: '2026-11-18' });
  assert.equal(x.tom, '3 chặng · đòi HTH 4.100.000 (cước 3.000.000, đóng ghép 500.000, phát sinh 500.000, chi hộ 200.000)');
  assert.deepEqual(x.canh.map(c => c.split(':')[0]), ['1 chặng chưa có giá', '1 chặng giá khác bảng giá', '1 chặng có ghi chú phát sinh chưa đọc được', 'Tháng 11 chưa hết']);
});

test('bảng giá: giá hôm nay, lịch giá sắp áp dụng, số chặng đổi theo tới bản giá kế tiếp', () => {
  const t = { gia: [{ tu_ngay: '2026-01-01', gia_vnd: '1000' }, { tu_ngay: '2026-11-10', gia_vnd: '1200' }, { tu_ngay: '2026-12-01', gia_vnd: '1300' }],
    cho_doi: ['2026-11-02', '2026-11-12', '2026-11-15', '2026-12-02'] };
  const g = T.giaHienTai(t, '2026-11-18');
  assert.equal(g.nay.gia_vnd, '1200');
  assert.deepEqual(g.sap.map(x => x.tu_ngay), ['2026-12-01']);
  assert.equal(T.soChangDoi(t, '2026-11-12'), 2);
  assert.equal(T.soChangDoi(t, '2026-11-01'), 1, 'bản giá 10/11 vẫn quyết định chặng từ 10/11');
  assert.equal(T.cachTinh({ cach: 'theo_ngay', muc_vnd: '1300000', muc_them_vnd: '1700000' }), 'Theo ngày: ngày đầu 1.300.000, mỗi ngày thêm 1.700.000');
  assert.equal(T.mucText({ cach: 'co_dinh', muc_vnd: null }), 'Chưa có mức');
  assert.equal(T.tenGoc('SAU DONG|KRONGPAK DAKLAK'), 'SAU DONG · KRONGPAK DAKLAK');
});

test('sửa khoản phát sinh: thân lệnh đúng cách tính, mức trống là chưa có mức, cần tên đọc được', () => {
  const p = { ma: 'neo', ten: 'Neo', cot: 'ps' };
  assert.deepEqual(T.psGui(p, { cach: 'theo_ngay', muc: '1.300.000', them: '1.700.000', chiHo: false, tenGoc: 'Neo, neo xe' }).body,
    { ma: 'neo', ten: 'Neo', cach: 'theo_ngay', muc_vnd: '1300000', muc_them_vnd: '1700000', chi_ho: false, cot: 'ps', ten_goc: ['Neo', 'neo xe'] });
  assert.equal(T.psGui(p, { cach: 'nhap_tay', muc: '5', them: '', chiHo: true, tenGoc: 'Cân' }).body.muc_vnd, null);
  assert.match(T.psGui(p, { cach: 'co_dinh', muc: '1,5', them: '', chiHo: true, tenGoc: 'x' }).loi, /Mức/);
  assert.match(T.psGui(p, { cach: 'co_dinh', muc: '', them: '', chiHo: true, tenGoc: ' , ' }).loi, /tên đọc được/);
});

test('Lịch sử phần thu: câu đọc được, có trước → sau', () => {
  assert.equal(T.moTa({ viec: 'dieu_chinh_bk', truoc: { thang: '2026-10-01', container: 'MAUU1000001', doi_vnd: '4100000' },
    sau: { so_tien_vnd: '-380000', doi_vnd: '3720000' } }), 'Điều chỉnh tháng 10/2026, dòng MAUU1000001: −380.000. Đòi HTH 4.100.000 → 3.720.000');
  assert.equal(T.moTa({ viec: 'ghi_tien_ve', truoc: { con_vnd: '3720000' }, sau: { thang: '2026-10-01', ngay: '2026-11-18', so_tien_vnd: '3720000', con_vnd: '0' } }),
    'HTH trả tháng 10/2026 ngày 18/11: 3.720.000. Còn phải thu 3.720.000 → 0');
  assert.match(T.moTa({ viec: 'sua_gia', truoc: { tuyen: 'Hàng giả · Tỉnh giả' }, sau: { gia_vnd: '1200', tu_ngay: '2026-12-01', so_chang: 2 } }), /2 chặng tháng đang gom đổi theo/);
});
