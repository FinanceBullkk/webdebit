/* Đội xe đợt 2 (DOI-XE-THU-01, specs/doi-xe-thu-01.md): đọc chữ, kiểm ô và tính trước → sau của màn Bảng kê gửi HTH và Bảng
 * giá (ARCH-03: tiền chỉ tính ở model). Số đòi, tổng dòng, công nợ cước do hàm SQL `doixe.*` tính; ở đây chỉ cộng trừ để cho
 * người dùng thấy số trước → sau khi đang gõ, và chặn ô sai trước khi gửi. Tiền từ API là chuỗi số nguyên VND; ô trống là null,
 * không phải 0. Dùng lại cách đọc số, ngày của doi-xe-model.js. Không gọi mạng, không đụng DOM; test ở test-doi-xe-thu-model.js. */
(function (root, factory) {
  const base = typeof module === 'object' && module.exports ? require('./doi-xe-model.js') : root.DoiXeModel;
  const api = factory(base);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DoiXeThuModel = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, M => {
  'use strict';
  const { so, fmt, fmtDau, ddmm, ddmmyyyy, docTien, docNgayGo, docNgayApGia, khoanTrung } = M;

  const LOAI_PHU = { chuyen_cang: 'Chuyển cảng', tra_rong: 'Trả rỗng', rut_mooc: 'Rút mooc', tha_mooc: 'Thả mooc', khac: 'Khác' };
  const thangSo = iso => Number(String(iso).slice(5, 7));
  const tenThang = iso => `${thangSo(iso)}/${String(iso).slice(0, 4)}`;

  // ---- Trạng thái bảng kê: đang gom → đã gửi (đang đối chiếu) → chờ HTH trả → thu đủ ----
  function trangThai(data) {
    const bk = data.bang_ke;
    if (!bk) return 'nhap';
    if (bk.trang_thai === 'da_gui') return 'gui';
    return bk.thu_du ? 'du' : 'doi';
  }
  const CHIP = { nhap: 'đang gom', gui: 'đang đối chiếu', doi: 'chờ HTH trả', du: 'thu đủ' };
  const NUT = { nhap: 'Gửi bảng kê', gui: 'Đối chiếu xong', doi: 'Ghi tiền HTH trả', du: '' };
  function nhanTrangThai(data) {
    const tt = trangThai(data), bk = data.bang_ke;
    if (tt === 'nhap') return 'Đang gom · chưa gửi';
    if (tt === 'gui') return `Đã gửi ${ddmm(bk.gui_ngay)} · đang đối chiếu`;
    if (tt === 'doi') return `Đã đối chiếu ${String(bk.doi_chieu_luc ?? '').slice(0, 5)} · chờ HTH trả`;
    const tra = (data.tien_ve ?? []).filter(v => !v.huy).slice(-1)[0];
    return `HTH trả đủ${tra ? ` ${ddmm(tra.ngay)}` : ''}`;
  }

  // Thanh tháng: tháng chưa thu đủ luôn hiện, cộng 4 tháng gần nhất và tháng đang xem; theo thứ tự thời gian.
  function cacThang(ds, dangXem) {
    const all = (ds ?? []).slice().sort((a, b) => (a.thang < b.thang ? -1 : 1));
    const gan = new Set(all.slice(-4).map(x => x.thang));
    return all.filter(x => x.trang_thai !== 'du' || gan.has(x.thang) || x.thang === dangXem);
  }

  // ---- Dòng ----
  const tien = v => (v === null || v === undefined ? null : so(v));
  // Tổng dòng như file debit: cước + đóng ghép + phát sinh; null khi cả ba trống.
  function tongDong(d) {
    const parts = [tien(d.cuoc_vnd), tien(d.ghep_vnd), tien(d.ps_vnd)].filter(v => v !== null);
    return parts.length ? parts.reduce((s, v) => s + v, 0) : null;
  }
  const dcDong = d => tien(d.dc_vnd) ?? 0;
  const khacGia = d => Boolean(d.cuoc_tay) && d.gia_bang_vnd !== null && d.gia_bang_vnd !== undefined && d.gia_bang_vnd !== d.cuoc_vnd;
  const LOC = [
    ['all', 'Tất cả', () => true],
    ['chuagia', 'Chưa có giá', d => d.cuoc_vnd === null],
    ['khacgia', 'Giá khác bảng', khacGia],
    ['chuadoc', 'Phát sinh chưa tính', d => (d.chua_doc ?? 0) > 0],
    ['khoanla', 'Khoản lạ', d => (d.khoan_la ?? 0) > 0],
    ['trung', 'Trùng dòng đã gửi', d => Boolean(d.trung_gui)],
    ['contlap', 'Container lặp', d => Array.isArray(d.cont_lap) && d.cont_lap.length > 0],
    ['bo', 'Chặng đã bỏ', d => d.chang_con === false],
    ['dc', 'Có điều chỉnh', d => d.dc_vnd !== null && d.dc_vnd !== undefined],
    ['phu', 'Chặng phụ', d => d.loai !== 'hang'],
  ];
  const locFn = k => (LOC.find(x => x[0] === k) ?? LOC[0])[2];
  // Chip lọc: luôn có Tất cả; chip khác chỉ hiện khi có dòng hoặc đang chọn.
  function locChips(dong, dangChon) {
    return LOC.map(([k, ten, f]) => ({ k, ten, n: dong.filter(f).length }))
      .filter(x => x.k === 'all' || x.n > 0 || x.k === dangChon);
  }
  // "Trước khi gửi": việc còn thiếu của tháng đang gom, mỗi việc mở đúng bộ lọc.
  function viecTruocGui(dong) {
    const n = k => dong.filter(locFn(k)).length;
    return [
      ['chuagia', `${n('chuagia')} chặng chưa có giá`],
      ['khacgia', `${n('khacgia')} chặng giá khác bảng giá`],
      ['chuadoc', `${n('chuadoc')} chặng có khoản phát sinh chưa tính được`],
      ['khoanla', `${n('khoanla')} chặng có khoản phát sinh chưa có trong danh mục`],
      ['trung', `${n('trung')} chặng trùng dòng đã gửi (cùng ngày, container)`],
      ['contlap', `${n('contlap')} chặng có container đã có chặng hàng khác trong 10 ngày`],
    ].filter(([k]) => n(k) > 0).map(([loc, text]) => ({ loc, text }));
  }
  // Tháng sau tháng này: chỉ có chặng ghi sau lúc gửi bảng kê tháng này, chưa gửi được.
  const thangToi = data => data.thang > data.hom_nay;
  // Tuyến hợp loại chặng (như doixe._tuyen_hop): hàng, rút/thả mooc theo tuyến hàng; chuyển cảng, trả rỗng theo tuyến cùng loại.
  const NHOM_HANG = ['hang', 'rut_mooc', 'tha_mooc'];
  const tuyenHop = (loaiChang, loaiTuyen) => (NHOM_HANG.includes(loaiChang) ? loaiTuyen === 'hang'
    : ['chuyen_cang', 'tra_rong'].includes(loaiChang) && loaiTuyen === loaiChang);
  // Nhớ tên gốc (HÀNG|TỈNH) chỉ cho chặng hàng, rút/thả mooc.
  const nhoDuoc = d => NHOM_HANG.includes(d.loai) && Boolean(d.khoa_tuyen) && d.khoa_tuyen !== '|';
  // Dòng tóm tắt dưới ba số: cước · đóng ghép · phát sinh (doanh thu) · chi hộ · điều chỉnh · số chặng.
  function coCau(tong) {
    const v = k => so(tong[k] ?? '0');
    const ps = v('ps_vnd') - v('chi_ho_vnd');
    return [`Cước ${fmt(v('cuoc_vnd'))}`, v('ghep_vnd') ? `Đóng ghép ${fmt(v('ghep_vnd'))}` : '', ps ? `Phát sinh ${fmt(ps)}` : '',
      v('chi_ho_vnd') ? `Chi hộ ${fmt(v('chi_ho_vnd'))}` : '', v('dc_vnd') ? `Điều chỉnh ${fmtDau(v('dc_vnd'))}` : '',
      `${tong.so_chang} chặng`].filter(Boolean).join(' · ');
  }
  function tenTuyen(d) {
    if (d.tuyen) return d.tuyen;
    const goc = [d.ten_hang, d.tinh].filter(x => x && String(x).trim()).join(' · ');
    return goc || (LOAI_PHU[d.loai] ?? '');
  }
  // Chi tiết khi bấm container: giá bảng, khác giá, từng khoản, điều chỉnh. Mỗi dòng {text, tone}.
  function chiTiet(d) {
    const out = [];
    const gb = tien(d.gia_bang_vnd);
    if (d.tuyen) {
      const mooc = d.loai === 'rut_mooc' || d.loai === 'tha_mooc';
      out.push({ text: `Bảng giá: ${d.tuyen} · ${gb === null ? 'chưa có giá ở ngày này' : fmt(gb)}${mooc && gb !== null ? ` (70% giá tuyến vì là ${LOAI_PHU[d.loai].toLowerCase()})` : ''}`, tone: gb === null ? 'canh' : '' });
    } else {
      out.push({ text: `Tuyến ${tenTuyen(d) || '(chưa ghi hàng, tỉnh)'} chưa có trong bảng giá.`, tone: 'canh' });
    }
    if (d.cuoc_tay) out.push({ text: `Giá cước nhập tay ${fmt(tien(d.cuoc_vnd))}${khacGia(d) ? `, khác bảng giá ${fmtDau(tien(d.cuoc_vnd) - gb)}` : ''}.`, tone: khacGia(d) ? 'canh' : '' });
    // Khoản lấy từ ô ngày neo, giờ máy phát của chặng (phiếu chi mới) ghi rõ nguồn.
    const o = it => (it.o ? ` (theo ô ${it.ma === 'neo' ? 'Ngày neo' : 'Giờ máy'})` : '');
    for (const it of d.ps ?? []) {
      if (it.loi) out.push({ text: it.o ? `${it.goc}${o(it)} chưa tính: ${it.loi}.` : `Ghi chú chưa đọc được: «${it.goc}». ${it.loi}.`, tone: 'canh' });
      else out.push({ text: `${it.ten}: ${fmt(so(it.so_tien_vnd))}${o(it)}${it.chi_ho ? ' · chi hộ' : ''}${it.la ? ' · chưa có trong danh mục' : ''}`, tone: it.la ? 'canh' : '' });
    }
    for (const a of d.dieu_chinh ?? []) out.push({ text: `Điều chỉnh ${fmtDau(so(a.so_tien_vnd))} · ${a.ly_do} · ${a.actor_name ?? a.actor} ${a.luc}`, tone: 'dc' });
    if (d.chang_con === false) out.push({ text: 'Chặng này đã xóa hoặc bỏ ở sổ tài xế sau khi gửi: cần thì ghi điều chỉnh.', tone: 'canh' });
    if (Array.isArray(d.cont_lap) && d.cont_lap.length) out.push({ text: `Container này còn chặng hàng ngày ${d.cont_lap.map(ddmm).join(', ')} (lệch tới 10 ngày). Nếu là một chuyến bị dán hai lần (Sheet sửa ngày rồi dán lại): xóa chặng thừa ở sổ tài xế, tránh đòi HTH hai lần.`, tone: 'canh' });
    if (d.trung_gui) out.push({ text: `Cùng ngày, container với một dòng đã gửi ở bảng kê tháng ${tenThang(d.trung_gui)}. Nếu là chặng đã gửi bị nhập lại: xóa chặng thừa ở sổ tài xế, hoặc gửi rồi ghi điều chỉnh bớt dòng này.`, tone: 'canh' });
    return out;
  }

  // ---- Điều chỉnh dòng (bảng kê đã gửi) ----
  // dau: 'bot' | 'them'. Trả {v (có dấu) | null, loi, xem (trước → sau)}.
  function dcXem(tong, d, dau, tienText, lyDo) {
    const doi = so(tong.doi_vnd), dong = (tongDong(d) ?? 0) + dcDong(d);
    const t = docTien(tienText);
    if (t.loi) return { v: null, loi: `Số tiền: ${t.loi.toLowerCase()}. VND là số nguyên.`, xem: `Đòi HTH hiện tại: ${fmt(doi)}` };
    if (t.v === null || t.v === 0) return { v: null, loi: 'Nhập số tiền điều chỉnh.', xem: `Đòi HTH hiện tại: ${fmt(doi)}` };
    const v = dau === 'bot' ? -t.v : t.v;
    const xem = `Đòi HTH: ${fmt(doi)} → ${fmt(doi + v)} · dòng này ${fmt(dong)} → ${fmt(dong + v)}`;
    if (dong + v < 0) return { v: null, loi: `Bớt nhiều hơn tổng dòng (${fmt(dong)}).`, xem };
    if (!String(lyDo ?? '').trim()) return { v, loi: 'Ghi lý do: HTH thắc mắc gì, ai báo.', xem };
    return { v, loi: '', xem };
  }

  // ---- Tiền về (bảng kê đã đối chiếu) ----
  function tvXem(data, ngayText, tienText) {
    const con = so(data.tong.con_vnd), m = tenThang(data.thang);
    const ng = docNgayGo(ngayText, data.hom_nay);
    const t = docTien(tienText);
    let loi = '', canh = '', xem = `Còn phải thu: ${fmt(con)}`;
    if (ng.loi || !ng.v) loi = ng.loi ? 'Ngày không đọc được. Ghi ngày kiểu 14/11.' : 'Nhập ngày tiền về.';
    else if (ng.v > data.hom_nay) loi = 'Ngày tiền về sau hôm nay: không ghi trước được.';
    else if (data.bang_ke && ng.v < data.bang_ke.gui_ngay) loi = `Ngày tiền về trước ngày gửi bảng kê (${ddmm(data.bang_ke.gui_ngay)}).`;
    if (!loi) {
      if (t.loi) loi = `Số tiền: ${t.loi.toLowerCase()}. VND là số nguyên.`;
      else if (!t.v) loi = 'Nhập số tiền HTH đã chuyển.';
      else if (t.v > con) loi = `Lớn hơn số còn phải thu (${fmt(con)}). HTH trả trước cho tháng sau thì ghi ở tháng sau.`;
    }
    if (t.v && !t.loi) {
      xem = `Còn phải thu: ${fmt(con)} → ${fmt(Math.max(con - t.v, 0))}`;
      if (t.v < con) canh = `Trả thiếu ${fmt(con - t.v)}: tháng ${m} vẫn chờ phần còn lại.`;
    }
    // Đã có lần tiền về cùng ngày, cùng số (audit DX-03): hỏi lại trước khi ghi, tránh hai người ghi cùng một lần chuyển khoản.
    const tr = ng.v && t.v ? khoanTrung(data.tien_ve, ng.v, t.v) : null;
    const trung = tr ? `Đã có lần tiền về ${ddmm(tr.ngay)} đúng ${fmt(t.v)} (${tr.actor_name ?? tr.actor} ghi ${tr.luc}). Ghi thêm lần nữa chỉ khi HTH chuyển hai lần.` : '';
    return { ngay: ng.v ?? null, v: t.v ?? null, loi, canh, xem, trung };
  }
  const huyXem = (con, tienVe) => `Còn phải thu: ${fmt(con)} → ${fmt(con + so(tienVe.so_tien_vnd))}`;

  // ---- Gửi bảng kê ----
  function guiXem(data) {
    const t = data.tong, v = k => so(t[k] ?? '0');
    const tom = `${t.so_chang} chặng · đòi HTH ${fmt(v('doi_vnd'))} (cước ${fmt(v('cuoc_vnd'))}, đóng ghép ${fmt(v('ghep_vnd'))}, phát sinh ${fmt(v('ps_vnd') - v('chi_ho_vnd'))}, chi hộ ${fmt(v('chi_ho_vnd'))})`;
    const canh = [];
    if (t.chua_gia) canh.push(`${t.chua_gia} chặng chưa có giá: ô cước để trống, chưa tính vào số đòi.`);
    if (t.khac_gia) canh.push(`${t.khac_gia} chặng giá khác bảng giá: gửi theo giá đang dùng.`);
    if (t.chua_doc) canh.push(`${t.chua_doc} chặng có khoản phát sinh chưa tính được (ghi chú chưa đọc được hoặc chưa có mức): khoản đó chưa tính.`);
    if (t.khoan_la) canh.push(`${t.khoan_la} chặng có khoản phát sinh chưa có trong danh mục: vẫn tính, không phải chi hộ.`);
    if (t.cont_lap) canh.push(`${t.cont_lap} chặng có container đã có chặng hàng khác trong 10 ngày: xem có phải một chuyến bị dán hai lần không.`);
    if (t.trung) canh.push(`${t.trung} chặng cùng ngày, container với dòng đã gửi: xem có phải chặng đã gửi bị nhập lại không, tránh đòi HTH hai lần.`);
    if (data.thang === `${data.hom_nay.slice(0, 7)}-01`) canh.push(`Tháng ${thangSo(data.thang)} chưa hết: chặng ghi sau lúc gửi vào bảng kê tháng sau.`);
    return { tom, canh };
  }
  // ---- Đối chiếu xong: sau bước này không ghi điều chỉnh nữa, nên nhắc dòng còn thiếu tiền hay chặng đã bỏ ----
  function doiChieuCanh(data) {
    const t = data.tong, canh = [];
    if (t.chua_gia) canh.push(`${t.chua_gia} dòng chưa có giá: đối chiếu xong thì không thêm tiền cho các dòng này được nữa. Cần đòi thì ghi điều chỉnh trước.`);
    if (t.chang_bo) canh.push(`${t.chang_bo} dòng có chặng đã xóa hoặc bỏ ở sổ tài xế sau khi gửi: không đòi thì ghi điều chỉnh bớt trước.`);
    return canh;
  }

  // ---- Bảng giá ----
  function giaHienTai(t, homNay) {
    const ds = (t.gia ?? []).slice().sort((a, b) => (a.tu_ngay < b.tu_ngay ? -1 : 1));
    const nay = ds.filter(g => g.tu_ngay <= homNay).slice(-1)[0] ?? null;
    return { nay, sap: ds.filter(g => g.tu_ngay > homNay) };
  }
  // Số chặng đang gom theo bảng giá của tuyến sẽ đổi khi thêm giá từ ngày `tu`: ngày chặng ≥ tu và chưa tới bản giá kế tiếp.
  function soChangDoi(t, tu) {
    if (!tu) return 0;
    const sau = (t.gia ?? []).map(g => g.tu_ngay).filter(x => x > tu).sort()[0] ?? null;
    return (t.cho_doi ?? []).filter(d => d >= tu && (sau === null || d < sau)).length;
  }
  // Ô đổi giá (audit DX-01): ngày áp dụng đọc kiểu Bảng giá, câu xem trước in đủ ngày/tháng/năm. `cu`: trước tháng này (áp ngược,
  // phải xác nhận).
  function giaXem(t, tuText, homNay) {
    const ng = docNgayApGia(tuText, homNay);
    if (!ng.v) return { v: null, cu: false, note: 'Ghi ngày áp dụng kiểu 01/12/2026.' };
    const n = soChangDoi(t, ng.v);
    const note = `Áp dụng từ ${ddmmyyyy(ng.v)}. Tháng đã gửi HTH giữ giá cũ; chặng đang gom từ ${ddmmyyyy(ng.v)} đổi theo giá mới: ${n} chặng.`
      + (ng.cu ? ` Ngày này trước tháng ${tenThang(homNay)}: giá áp ngược.` : '');
    return { v: ng.v, cu: Boolean(ng.cu), n, note };
  }
  function cachTinh(p) {
    const muc = p.muc_vnd === null || p.muc_vnd === undefined ? null : so(p.muc_vnd);
    if (p.cach === 'theo_ngay') return muc === null ? 'Theo ngày (chưa có mức)' : `Theo ngày: ngày đầu ${fmt(muc)}, mỗi ngày thêm ${fmt(so(p.muc_them_vnd ?? '0'))}`;
    if (p.cach === 'theo_don_vi') return muc === null ? 'Theo số đơn vị (chưa có mức)' : `Theo số đơn vị: ${fmt(muc)} mỗi đơn vị`;
    if (p.cach === 'co_dinh') return 'Cố định';
    return p.cot === 'ghep' ? 'Nhập tay theo chuyến (số kho, khoảng cách)' : 'Nhập tay';
  }
  const mucText = p => (p.cach === 'nhap_tay' ? 'Nhập tay' : p.muc_vnd === null || p.muc_vnd === undefined ? 'Chưa có mức' : fmt(so(p.muc_vnd)));
  // Tên gốc lưu dạng 'HÀNG|TỈNH' (chuẩn hóa) → 'HÀNG · TỈNH' để đọc.
  const tenGoc = khoa => String(khoa).split('|').filter(Boolean).join(' · ');

  // Ô sửa phát sinh → thân lệnh; trả {body} hoặc {loi}.
  function psGui(p, f) {
    const muc = docTien(f.muc), them = docTien(f.them);
    if (f.cach !== 'nhap_tay' && muc.loi) return { loi: `Mức: ${muc.loi.toLowerCase()}.` };
    if (f.cach === 'theo_ngay' && them.loi) return { loi: `Mức thêm mỗi ngày: ${them.loi.toLowerCase()}.` };
    if (f.cach !== 'nhap_tay' && muc.v === 0) return { loi: 'Mức phải lớn hơn 0, hoặc để trống.' };
    const tens = String(f.tenGoc ?? '').split(/[,;\n]/).map(x => x.trim()).filter(Boolean);
    if (!tens.length) return { loi: 'Cần ít nhất một tên đọc được trong ghi chú.' };
    return { body: { ma: p.ma, ten: p.ten, cach: f.cach, muc_vnd: f.cach === 'nhap_tay' || muc.v === null ? null : String(muc.v),
      muc_them_vnd: f.cach === 'theo_ngay' && them.v !== null ? String(them.v) : null, chi_ho: Boolean(f.chiHo), cot: p.cot, ten_goc: tens } };
  }

  // ---- Lịch sử phần thu ----
  function moTa(e) {
    const t = e.truoc ?? {}, s = e.sau ?? {};
    const v = x => (x === null || x === undefined ? '—' : fmt(so(x)));
    switch (e.viec) {
      case 'gui_bang_ke': return `Gửi bảng kê tháng ${tenThang(s.thang)} cho HTH: đòi ${v(s.doi_vnd)}${s.chua_gia ? ` (${s.chua_gia} chặng chưa có giá, chưa tính cước)` : ''}`;
      case 'doi_chieu_xong': return `Đối chiếu xong tháng ${tenThang(s.thang)}: HTH đồng ý đòi ${v(s.doi_vnd)}`;
      case 'dieu_chinh_bk': return `Điều chỉnh tháng ${tenThang(t.thang)}, dòng ${t.container}: ${fmtDau(so(s.so_tien_vnd))}. Đòi HTH ${v(t.doi_vnd)} → ${v(s.doi_vnd)}`;
      case 'ghi_tien_ve': return `HTH trả tháng ${tenThang(s.thang)} ngày ${ddmm(s.ngay)}: ${v(s.so_tien_vnd)}. Còn phải thu ${v(t.con_vnd)} → ${v(s.con_vnd)}`;
      case 'huy_tien_ve': return `Hủy lần tiền về ${ddmm(t.ngay)} (${v(t.so_tien_vnd)}) tháng ${tenThang(t.thang)}. Còn phải thu ${v(t.con_vnd)} → ${v(s.con_vnd)}`;
      case 'sua_cuoc': return `Giá cước dòng ${t.container} (${ddmm(t.ngay)}): ${v(t.cuoc_vnd)} → ${v(s.cuoc_vnd)}${s.cuoc_tay ? '' : ' (theo bảng giá)'}`;
      case 'gan_tuyen': return `Gắn tuyến dòng ${t.container} (${ddmm(t.ngay)})${s.nho ? `, nhớ cho chặng ghi «${tenGoc(t.khoa ?? '')}»: ${s.so_chang} chặng` : ''}`;
      case 'sua_gia': return `Bảng giá ${t.tuyen}: ${v(s.gia_vnd)} từ ${ddmmyyyy(s.tu_ngay)}. ${s.so_chang} chặng tháng đang gom đổi theo; tháng đã gửi giữ giá cũ`;
      case 'luu_tuyen': return t.tuyen_id ? `Sửa tuyến ${s.ten}${s.dang_dung === false ? ' (ngưng dùng)' : ''}` : `Thêm tuyến ${s.ten}: ${v(s.gia_vnd)} từ ${ddmmyyyy(s.tu_ngay)}`;
      case 'luu_phat_sinh': return `Danh mục phát sinh: ${s.ten}${s.chi_ho ? ' (chi hộ)' : ''}`;
      default: return e.viec;
    }
  }

  return { LOAI_PHU, thangSo, tenThang, trangThai, CHIP, NUT, nhanTrangThai, cacThang, tien, tongDong, dcDong, khacGia, LOC, locFn,
    locChips, viecTruocGui, thangToi, tuyenHop, nhoDuoc, coCau, tenTuyen, chiTiet, dcXem, tvXem, huyXem, guiXem, doiChieuCanh,
    giaHienTai, soChangDoi, giaXem, cachTinh, mucText, tenGoc, psGui, moTa };
}));
