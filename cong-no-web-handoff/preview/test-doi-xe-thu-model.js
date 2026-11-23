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
  assert.deepEqual(T.viecTruocGui(dong).map(x => x.text), ['1 chặng chưa có giá', '1 chặng giá khác bảng giá', '1 chặng có khoản phát sinh chưa tính được']);
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
  // Khoản lấy từ ô ngày neo, giờ máy phát của chặng (phiếu chi mới) ghi rõ nguồn.
  const tuO = T.chiTiet(line({ ps: [{ goc: 'Neo 2 ngày', ten: 'Neo 2 ngày', ma: 'neo', so_tien_vnd: '3000000', chi_ho: false, o: true },
    { goc: 'Nổ máy phát 3 giờ', ma: 'no_may', o: true, loi: 'Khoản này chưa có mức: ghi mức ở Bảng giá hoặc ghi số tiền vào ghi chú' }] })).map(x => x.text);
  assert.equal(tuO[1], 'Neo 2 ngày: 3.000.000 (theo ô Ngày neo)');
  assert.equal(tuO[2], 'Nổ máy phát 3 giờ (theo ô Giờ máy) chưa tính: Khoản này chưa có mức: ghi mức ở Bảng giá hoặc ghi số tiền vào ghi chú.');
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
  assert.deepEqual(x.canh.map(c => c.split(':')[0]), ['1 chặng chưa có giá', '1 chặng giá khác bảng giá', '1 chặng có khoản phát sinh chưa tính được (ghi chú chưa đọc được hoặc chưa có mức)', 'Tháng 11 chưa hết']);
  const trung = T.guiXem({ tong: { ...tong, chua_gia: 0, khac_gia: 0, chua_doc: 0, trung: 2 }, thang: '2026-10-01', hom_nay: '2026-11-18' });
  assert.deepEqual(trung.canh, ['2 chặng cùng ngày, container với dòng đã gửi: xem có phải chặng đã gửi bị nhập lại không, tránh đòi HTH hai lần.']);
});

test('chặng trùng dòng đã gửi, chặng đã bỏ: lọc, việc trước khi gửi, chi tiết; tháng sau chưa gửi được', () => {
  const dong = [line({ chang_id: 1, trung_gui: '2026-10-01' }), line({ chang_id: 2, trung_gui: null }), line({ chang_id: 3, chang_con: false })];
  assert.deepEqual(dong.filter(T.locFn('trung')).map(d => d.chang_id), [1]);
  assert.deepEqual(dong.filter(T.locFn('bo')).map(d => d.chang_id), [3]);
  assert.deepEqual(T.viecTruocGui(dong.slice(0, 2)), [{ loc: 'trung', text: '1 chặng trùng dòng đã gửi (cùng ngày, container)' }]);
  assert.match(T.chiTiet(dong[0]).map(c => c.text).join('\n'), /Cùng ngày, container với một dòng đã gửi ở bảng kê tháng 10\/2026/);
  assert.equal(T.thangToi({ thang: '2026-12-01', hom_nay: '2026-11-18' }), true);
  assert.equal(T.thangToi({ thang: '2026-11-01', hom_nay: '2026-11-18' }), false);
});

test('tuyến hợp loại chặng và nhớ tên gốc chỉ cho chặng hàng (như doixe._tuyen_hop)', () => {
  assert.deepEqual(['hang', 'rut_mooc', 'tha_mooc', 'chuyen_cang', 'tra_rong', 'khac'].map(l => [T.tuyenHop(l, 'hang'), T.tuyenHop(l, 'chuyen_cang')]),
    [[true, false], [true, false], [true, false], [false, true], [false, false], [false, false]]);
  assert.equal(T.tuyenHop('tra_rong', 'tra_rong'), true);
  assert.equal(T.nhoDuoc(line({ loai: 'rut_mooc', khoa_tuyen: 'HANG GIA|TINH GIA' })), true);
  assert.equal(T.nhoDuoc(line({ loai: 'chuyen_cang', khoa_tuyen: 'HANG GIA|TINH GIA' })), false);
  assert.equal(T.nhoDuoc(line({ khoa_tuyen: '|' })), false);
});

test('đối chiếu xong: nhắc dòng chưa có giá và chặng đã bỏ, vì sau bước này không điều chỉnh được nữa', () => {
  assert.deepEqual(T.doiChieuCanh({ tong: { ...tong, chua_gia: 0, chang_bo: 0 } }), []);
  const canh = T.doiChieuCanh({ tong: { ...tong, chua_gia: 2, chang_bo: 1 } });
  assert.deepEqual(canh.map(c => c.split(':')[0]), ['2 dòng chưa có giá', '1 dòng có chặng đã xóa hoặc bỏ ở sổ tài xế sau khi gửi']);
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

test('đổi giá (audit DX-01): câu xem trước in đủ ngày/tháng/năm, đếm chặng đổi; ngày trước tháng này là áp ngược', () => {
  const t = { gia: [{ tu_ngay: '2026-01-01', gia_vnd: '10000000' }], cho_doi: ['2026-11-20', '2026-12-02', '2026-12-03'] };
  const sang = T.giaXem(t, '01/01', '2026-12-05');
  assert.equal(sang.v, '2027-01-01');
  assert.equal(sang.cu, false);
  assert.equal(sang.note, 'Áp dụng từ 01/01/2027. Tháng đã gửi HTH giữ giá cũ; chặng đang gom từ 01/01/2027 đổi theo giá mới: 0 chặng.');
  const nguoc = T.giaXem(t, '01/01/2026', '2026-12-05');
  assert.equal(nguoc.cu, true);
  assert.equal(nguoc.n, 3);
  assert.match(nguoc.note, /^Áp dụng từ 01\/01\/2026\..*: 3 chặng\. Ngày này trước tháng 12\/2026: giá áp ngược\.$/);
  assert.equal(T.giaXem(t, '01/12', '2026-12-05').n, 2);
  assert.deepEqual(T.giaXem(t, 'abc', '2026-12-05'), { v: null, cu: false, note: 'Ghi ngày áp dụng kiểu 01/12/2026.' });
});

test('tiền về trùng (audit DX-03): đã có lần chưa hủy cùng ngày, cùng số thì báo; khoản đã hủy hay khác số thì không', () => {
  const data = { thang: '2026-10-01', hom_nay: '2026-11-18', tong, bang_ke: { gui_ngay: '2026-11-03' },
    tien_ve: [{ id: 1, ngay: '2026-11-10', so_tien_vnd: '1000000', huy: null, actor: 'kt@gia', luc: '10/11 09:00' },
      { id: 2, ngay: '2026-11-11', so_tien_vnd: '1000000', huy: { ly_do: 'nhầm' } }] };
  assert.match(T.tvXem(data, '10/11', '1.000.000').trung, /^Đã có lần tiền về 10\/11 đúng 1\.000\.000 \(kt@gia ghi 10\/11 09:00\)/);
  assert.equal(T.tvXem(data, '11/11', '1.000.000').trung, '', 'lần đã hủy không tính');
  assert.equal(T.tvXem(data, '10/11', '900.000').trung, '');
  assert.equal(T.tvXem({ ...data, tien_ve: [] }, '10/11', '1.000.000').trung, '');
});

test('container lặp (audit DX-04): lọc, việc trước khi gửi, chi tiết, cảnh báo khi gửi', () => {
  const dong = [line({ chang_id: 1, cont_lap: ['2026-11-04'] }), line({ chang_id: 2, cont_lap: null }), line({ chang_id: 3 })];
  assert.deepEqual(dong.filter(T.locFn('contlap')).map(d => d.chang_id), [1]);
  assert.deepEqual(T.viecTruocGui(dong), [{ loc: 'contlap', text: '1 chặng có container đã có chặng hàng khác trong 10 ngày' }]);
  assert.ok(T.locChips(dong, 'all').some(c => c.k === 'contlap' && c.n === 1));
  assert.match(T.chiTiet(dong[0]).map(c => c.text).join('\n'), /Container này còn chặng hàng ngày 04\/11 \(lệch tới 10 ngày\)/);
  const x = T.guiXem({ tong: { ...tong, chua_gia: 0, khac_gia: 0, chua_doc: 0, cont_lap: 2 }, thang: '2026-10-01', hom_nay: '2026-11-18' });
  assert.deepEqual(x.canh, ['2 chặng có container đã có chặng hàng khác trong 10 ngày: xem có phải một chuyến bị dán hai lần không.']);
});
