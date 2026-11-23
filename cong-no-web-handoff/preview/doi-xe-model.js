/* Đội xe đợt 1 (CHI-PHI-XE-01, specs/chi-phi-xe-01.md): mọi phép đọc chữ, kiểm dòng và tính tiền của màn Đội xe (ARCH-03:
 * tiền chỉ tính ở model). Không gọi mạng, không đụng DOM; test ở test-doi-xe-model.js. Số tiền từ API là chuỗi số nguyên VND,
 * đổi sang Number sau khi kiểm an toàn (dưới 2^53); ô trống là null, không phải 0. Luật ghi vẫn do hàm SQL `doixe.*` giữ:
 * phần kiểm ở đây chỉ để báo lỗi tại ô trước khi gửi. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DoiXeModel = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  'use strict';

  const LOAI = [['hang', 'Hàng'], ['chuyen_cang', 'Chuyển cảng'], ['tra_rong', 'Trả rỗng'], ['rut_mooc', 'Rút mooc'],
    ['tha_mooc', 'Thả mooc'], ['khac', 'Khác']];
  const TEN_LOAI = Object.fromEntries(LOAI);
  const COT = { ngay: 2, cont: 3, contKeo: 4, tinh: 5, kho: 6, taiXe: 7, soXe: 8, lay: 9, ha: 10, hang: 11, ghiChu: 25, tong: 28 };

  const pad2 = n => (n < 10 ? '0' : '') + n;
  const so = value => {
    if (value === null || value === undefined) return null;
    const n = typeof value === 'number' ? value : Number(value);
    if (!Number.isSafeInteger(n)) throw Error(`Số tiền không hợp lệ: ${value}`);
    return n;
  };
  const fmt = n => (n === null || n === undefined ? '' : (n < 0 ? '−' : '') + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.'));
  const fmtDau = n => (n > 0 ? '+' : '') + fmt(n);
  const ddmm = iso => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '');
  const ddmmyyyy = iso => (iso ? `${ddmm(iso)}/${iso.slice(0, 4)}` : '');
  const thangCua = iso => (iso ? `${iso.slice(0, 7)}-01` : '');
  const boDau = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
  const chuSo = s => String(s ?? '').replace(/\D/g, '');

  // "= 3 triệu 500 nghìn đồng": đọc số tiền thành chữ ngắn để người nhập thấy ngay gõ thừa hay thiếu số 0.
  function docSo(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return '';
    if (n === 0) return 'không đồng';
    const a = Math.abs(n);
    const phan = [];
    const ty = Math.floor(a / 1e9), tr = Math.floor((a % 1e9) / 1e6), ng = Math.floor((a % 1e6) / 1e3), d = a % 1e3;
    if (ty) phan.push(`${ty} tỷ`);
    if (tr) phan.push(`${tr} triệu`);
    if (ng) phan.push(`${ng} nghìn`);
    if (d) phan.push(`${d} đồng`);
    return (n < 0 ? 'âm ' : '') + phan.join(' ');
  }

  // Ô tiền: trống/gạch là null; số nguyên có hoặc không nhóm nghìn; số lẻ, âm, chữ là lỗi (giữ nguyên chữ để sửa tại ô).
  function docTien(text) {
    const t = String(text ?? '').replace(/[\sđ₫]/g, '');
    if (t === '' || t === '-' || t === '–' || t === '—') return { v: null };
    if (/^[-−]/.test(t)) return { loi: 'Số âm' };
    let v;
    if (/^\d+$/.test(t)) v = Number(t);
    else if (/^\d{1,3}([.,]\d{3})+$/.test(t)) v = Number(t.replace(/[.,]/g, ''));
    else if (/^[\d.,]+$/.test(t)) return { loi: 'Số lẻ' };
    else return { loi: 'Không phải số' };
    if (!Number.isSafeInteger(v) || v >= 1e16) return { loi: 'Số quá lớn' };
    return { v };
  }

  // Phiếu chi mới (11/2026): số lượng của chặng, không phải tiền. Số nguyên 1..max; trống là null; đơn vị gõ kèm được bỏ đi.
  const SO_LUONG = { neo_ngay: { max: 365, ten: 'Ngày neo' }, may_gio: { max: 999, ten: 'Giờ máy' }, km: { max: 9999, ten: 'Km' } };
  function docSoLuong(text, max) {
    const t = boDau(text).replace(/\s+/g, ' ').trim().replace(/\s*(ngay|h|gio|tieng|km)$/, '');
    if (t === '' || t === '-') return { v: null };
    if (/^\d+[.,]\d+$/.test(t)) return { loi: 'Số lẻ' };
    if (!/^\d+$/.test(t)) return { loi: 'Không phải số' };
    const v = Number(t);
    if (v === 0) return { loi: 'Số 0: để trống' };
    if (v > max) return { loi: `Quá ${max}` };
    return { v };
  }
  // Ô NỔ MÁY PHÁT trên Sheet ghi giờ kèm đơn vị ("5H", "3 TIẾNG"): là số giờ, không phải tiền.
  const gioMay = raw => { const m = boDau(raw).trim().match(/^(\d{1,3})\s*(h|gio|tieng)$/); return m && Number(m[1]) > 0 ? Number(m[1]) : null; };
  // Ô TỈNH theo phiếu mới ghi "huyện, tỉnh, km": lấy số km nếu có.
  const kmTinh = raw => { const m = boDau(raw).match(/(\d{1,4})\s*km(?![a-z])/); return m && Number(m[1]) > 0 ? Number(m[1]) : null; };

  function ngayHopLe(y, m, d) {
    if (m < 1 || m > 12 || d < 1 || d > 31 || y < 2020 || y > 2100) return { loi: 'Ngày lạ' };
    const dt = new Date(Date.UTC(y, m - 1, d));
    if (dt.getUTCMonth() + 1 !== m || dt.getUTCDate() !== d) return { loi: 'Ngày lạ' };
    return { v: `${y}-${pad2(m)}-${pad2(d)}` };
  }

  // Sheet chi phí ghi tháng/ngày/năm (10/2/2026 là 2/10). Số đầu lớn hơn 12 thì chắc là ngày/tháng.
  function docNgaySheet(text) {
    const t = String(text ?? '').trim();
    if (!t) return { v: null };
    let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(t);
    if (m) return ngayHopLe(+m[1], +m[2], +m[3]);
    m = /^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/.exec(t);
    if (!m) return { loi: 'Ngày lạ' };
    const a = +m[1], b = +m[2];
    let y = +m[3];
    if (y < 100) y += 2000;
    return a > 12 ? ngayHopLe(y, b, a) : ngayHopLe(y, a, b);
  }

  // Gõ trên web: ngày/tháng (năm của hôm nay) hoặc ngày/tháng/năm.
  function docNgayGo(text, homNay) {
    const t = String(text ?? '').trim();
    if (!t) return { v: null };
    const m = /^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$/.exec(t);
    if (!m) return { loi: 'Ngày lạ' };
    let y = m[3] ? +m[3] : +String(homNay).slice(0, 4);
    if (y < 100) y += 2000;
    return ngayHopLe(y, +m[2], +m[1]);
  }

  // Ngày áp dụng giá (Bảng giá, audit DX-01): như docNgayGo, nhưng gõ thiếu năm thì lấy năm gần nhất mà ngày không trước tháng này
  // (tháng 12 gõ 01/01 là 01/01 năm sau, không phải 01/01 năm nay). Muốn áp ngược về trước tháng này thì gõ đủ năm; `cu` báo
  // ngày đó trước tháng này để màn hỏi lại.
  function docNgayApGia(text, homNay) {
    const t = String(text ?? '').trim();
    if (!t) return { v: null };
    const m = /^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$/.exec(t);
    if (!m) return { loi: 'Ngày lạ' };
    const thangNay = thangCua(homNay);
    let r;
    if (m[3]) {
      let y = +m[3];
      if (y < 100) y += 2000;
      r = ngayHopLe(y, +m[2], +m[1]);
    } else {
      const y = +String(homNay).slice(0, 4);
      r = ngayHopLe(y, +m[2], +m[1]);
      if (r.v && r.v < thangNay) r = ngayHopLe(y + 1, +m[2], +m[1]);
    }
    return r.v ? { v: r.v, cu: r.v < thangNay } : r;
  }
  // Ô "Áp dụng từ ngày" mặc định: mùng 1 tháng sau, đủ năm.
  function ngayApMacDinh(homNay) {
    const y = +String(homNay).slice(0, 4), mo = +String(homNay).slice(5, 7);
    return mo === 12 ? `01/01/${y + 1}` : `01/${pad2(mo + 1)}/${y}`;
  }

  // Các tháng trên thanh tháng: tháng có dữ liệu, luôn thêm tháng trước và tháng này (sổ mới vẫn sang được tháng trước để dán),
  // và tháng đang xem; giữ 6 tháng gần nhất nhưng không bỏ tháng đang xem.
  function cacThang(thangCo, homNay, dangXem) {
    const nay = thangCua(homNay);
    const y = +nay.slice(0, 4), mo = +nay.slice(5, 7);
    const truoc = mo === 1 ? `${y - 1}-12-01` : `${y}-${pad2(mo - 1)}-01`;
    const ds = [...new Set([...(thangCo ?? []), truoc, nay, ...(dangXem ? [dangXem] : [])])].sort();
    const cuoi = ds.slice(-6);
    return dangXem && !cuoi.includes(dangXem) ? [dangXem, ...cuoi.slice(1)] : cuoi;
  }
  const chuanCont = text => String(text ?? '').toUpperCase().replace(/\s+/g, '');

  // Tách khối chép từ Sheet (TSV, ô có xuống dòng nằm trong ngoặc kép).
  function tachTSV(text) {
    const out = [];
    let row = [], cell = '', q = false, i = 0;
    const s = String(text ?? '').replace(/\r\n?/g, '\n');
    while (i < s.length) {
      const c = s[i];
      if (q) {
        if (c === '"') {
          if (s[i + 1] === '"') { cell += '"'; i += 2; continue; }
          q = false; i++; continue;
        }
        cell += c; i++; continue;
      }
      if (c === '"' && cell === '') { q = true; i++; continue; }
      if (c === '\t') { row.push(cell); cell = ''; i++; continue; }
      if (c === '\n') { row.push(cell); out.push(row); row = []; cell = ''; i++; continue; }
      cell += c; i++;
    }
    if (cell !== '' || row.length) { row.push(cell); out.push(row); }
    return out;
  }

  // Loại chặng đoán từ ghi chú; còn lại là Hàng.
  function doanLoai(ghiChu) {
    const g = boDau(ghiChu);
    if (/tra rong|ha rong/.test(g)) return 'tra_rong';
    if (/chuyen cang/.test(g)) return 'chuyen_cang';
    if (/rut mooc/.test(g)) return 'rut_mooc';
    if (/tha mooc/.test(g)) return 'tha_mooc';
    return 'hang';
  }

  // Số xe trên Sheet chỉ có chữ số: khớp đúng một xe theo các chữ số cuối của biển (ít nhất 4 chữ số); trống thì xe mặc định.
  function timXe(text, xeList, macDinh) {
    const dg = chuSo(text);
    if (!dg) return { v: macDinh ?? null };
    if (dg.length < 4) return { loi: 'Không rõ xe' };
    const khop = xeList.filter(x => x.dang_dung !== false && chuSo(x.bien_so).endsWith(dg));
    return khop.length === 1 ? { v: khop[0].id } : { loi: khop.length ? 'Số xe khớp nhiều xe' : 'Không rõ xe' };
  }

  const phiTien = loaiPhi => loaiPhi.filter(p => !p.cong_ty_tra).map(p => p.ma);

  // Một dòng dán (đủ 29 cột hoặc bắt đầu từ cột NGÀY) → dòng nháp. ctx: {xe, taiXe, nguoiTra, tra} mặc định theo sổ đang mở.
  function dongTuSheet(cells, ctx, loaiPhi, xeList) {
    const off = cells.length >= 28 ? 0 : -2;
    const g = i => { const v = cells[i + off]; return v === undefined || v === null ? '' : String(v).trim(); };
    if (/NG[ÀA]Y/i.test(g(COT.ngay)) && /CONT/i.test(g(COT.cont))) return { bo: 'tieude' };
    const ngay = docNgaySheet(g(COT.ngay));
    const container = chuanCont(g(COT.cont) || g(COT.contKeo));
    const phi = {}, loiO = {}, tho = {};
    let coTien = false, mayGio = null;
    for (const p of loaiPhi) {
      if (p.cot_sheet === null || p.cot_sheet === undefined) continue;
      const raw = g(p.cot_sheet);
      if (p.ma === 'may' && gioMay(raw) !== null) { mayGio = gioMay(raw); continue; }
      const r = docTien(raw);
      if (r.loi) { loiO[p.ma] = r.loi; tho[p.ma] = raw; coTien = true; } else if (r.v !== null) { phi[p.ma] = r.v; coTien = true; }
    }
    const ghiChu = g(COT.ghiChu).replace(/\s+/g, ' ');
    if (!g(COT.ngay) && !container && !coTien && !ghiChu) return { bo: 'trong' };
    const tong = docTien(g(COT.tong));
    const xe = timXe(g(COT.soXe), xeList, ctx.xe);
    const d = {
      raw: cells.join('\t'), ngay: ngay.v ?? '', ngayLoi: ngay.loi ?? '', container, loai: doanLoai(ghiChu),
      noi_lay: g(COT.lay), noi_ha: g(COT.ha), kho: g(COT.kho), tinh: g(COT.tinh), ten_hang: g(COT.hang), ghi_chu: ghiChu,
      xe: xe.v ?? null, xeLoi: xe.loi ?? '', phi, loiO, tho, tongSheet: tong.v ?? null,
      neo_ngay: null, may_gio: mayGio, km: kmTinh(g(COT.tinh)), loiSL: {}, thoSL: {},
    };
    return { d: hoanThien(d, ctx, xeList) };
  }

  // Tài xế và người trả của dòng nháp theo sổ đang mở: sổ tài xế giữ người đó; sổ người đi lệnh và sổ xe lấy tài xế của xe.
  function hoanThien(d, ctx, xeList) {
    const xe = xeList.find(x => x.id === d.xe);
    if (ctx.loai === 'tai_xe') {
      d.taiXe = ctx.nguoiId; d.nguoiTra = ctx.nguoiId;
    } else if (ctx.loai === 'di_lenh') {
      d.taiXe = xe?.tai_xe_id ?? null; d.nguoiTra = ctx.nguoiId;
    } else {
      d.taiXe = xe?.tai_xe_id ?? null; d.nguoiTra = xe?.tai_xe_id ?? null;
    }
    return d;
  }

  // Hàng trống (gõ tay) → dòng nháp.
  function nhapTuGo(moi, ctx, loaiPhi, xeList, homNay) {
    const ngay = docNgayGo(moi.ngay, homNay);
    const phi = {}, loiO = {}, tho = {};
    for (const p of loaiPhi) {
      const raw = moi.phi?.[p.ma] ?? '';
      const r = docTien(raw);
      if (r.loi) { loiO[p.ma] = r.loi; tho[p.ma] = raw; } else if (r.v !== null) phi[p.ma] = r.v;
    }
    const d = {
      raw: '', ngay: ngay.v ?? '', ngayLoi: ngay.loi ?? '', container: chuanCont(moi.container), loai: moi.loai || 'hang',
      noi_lay: (moi.noi_lay ?? '').trim(), noi_ha: (moi.noi_ha ?? '').trim(), kho: (moi.kho ?? '').trim(), tinh: '', ten_hang: '',
      ghi_chu: (moi.ghi_chu ?? '').trim(), xe: moi.xe ? Number(moi.xe) : ctx.xe ?? null, xeLoi: '', phi, loiO, tho, tongSheet: null,
      loiSL: {}, thoSL: {},
    };
    for (const [k, sl] of Object.entries(SO_LUONG)) ganSoLuong(d, k, moi[k] ?? '', sl.max);
    return hoanThien(d, ctx, xeList);
  }

  // Gán một ô số lượng của dòng nháp: lỗi giữ nguyên chữ đã gõ để sửa tại ô.
  function ganSoLuong(d, k, text, max) {
    const r = docSoLuong(text, max);
    d.loiSL ??= {}; d.thoSL ??= {};
    if (r.loi) { d.loiSL[k] = r.loi; d.thoSL[k] = String(text); d[k] = null; } else { delete d.loiSL[k]; delete d.thoSL[k]; d[k] = r.v; }
  }

  const moiCo = moi => Boolean(moi && (moi.ngay || moi.container || moi.noi_lay || moi.noi_ha || moi.kho || moi.ghi_chu
    || Object.keys(SO_LUONG).some(k => String(moi[k] ?? '').trim())
    || Object.values(moi.phi ?? {}).some(v => String(v ?? '').trim())));

  const khoaChang = d => `${d.ngay}|${d.container}|${d.loai}|${d.xe}`;
  const khoaDaLuu = c => `${c.ngay}|${c.container}|${c.loai}|${c.xe_id}`;

  // Tổng tài xế chi của dòng nháp (mọi phí trừ phí công ty trả); null khi không có ô nào.
  function chiNhap(d, loaiPhi) {
    let s = null;
    for (const ma of phiTien(loaiPhi)) if (d.phi[ma] !== undefined && d.phi[ma] !== null) s = (s ?? 0) + d.phi[ma];
    return s;
  }

  // Kiểm dòng nháp: trả {loiCot, loi (lỗi đầu tiên), canhBao}. `daLuu` là khóa chặng đã lưu đang biết; `nhap` là mọi dòng nháp.
  function kiemDong(d, daLuu, nhap, loaiPhi, homNay) {
    const loiCot = { ...d.loiO, ...d.loiSL };
    const coTien = loaiPhi.some(p => d.phi[p.ma] !== undefined) || Object.keys(d.loiO).length > 0;
    if (!d.ngay && !d.container && coTien) {
      loiCot.ngay = 'Có tiền, thiếu ngày và cont';
      loiCot.container = 'Có tiền, thiếu ngày và cont';
    } else {
      if (d.ngayLoi) loiCot.ngay = d.ngayLoi;
      else if (!d.ngay) loiCot.ngay = 'Thiếu ngày';
      else if (d.ngay > homNay) loiCot.ngay = 'Ngày sau hôm nay';
      if (!d.container) loiCot.container = coTien ? 'Có tiền, thiếu cont' : 'Thiếu cont';
      else if (d.container.length > 20) loiCot.container = 'Cont quá dài';
    }
    if (d.xeLoi) loiCot.xe = d.xeLoi;
    else if (!d.xe) loiCot.xe = 'Chưa chọn xe';
    if (d.loiMay) loiCot[d.loiMay.cot] = d.loiMay.ma;
    if (!Object.keys(loiCot).length) {
      const k = khoaChang(d);
      if (daLuu.has(k) || nhap.some(x => x !== d && khoaChang(x) === k)) loiCot.container = 'Đã có chặng này';
    }
    const thu = ['ngay', 'container', 'xe', ...Object.keys(SO_LUONG), ...loaiPhi.map(p => p.ma)];
    const dau = thu.find(c => loiCot[c]);
    let canhBao = '';
    if (!dau && d.tongSheet !== null) {
      const c = chiNhap(d, loaiPhi) ?? 0;
      if (c !== d.tongSheet) canhBao = `Sheet ghi tổng ${fmt(d.tongSheet)}`;
    }
    return { loiCot, loi: dau ? loiCot[dau] : '', canhBao };
  }

  // Dán một khối: bỏ tiêu đề, dòng trống, dòng đã có (lưu rồi hoặc đang nháp, kể cả dán lại đúng khối cũ).
  function danKhoi(text, ctx, loaiPhi, xeList, daLuu, nhap) {
    const keys = new Set(daLuu);
    const raws = new Set();
    for (const d of nhap) { keys.add(khoaChang(d)); if (d.raw) raws.add(d.raw); }
    const moi = [];
    let daCo = 0, trong = 0, tong = 0;
    for (const cells of tachTSV(text)) {
      const kq = dongTuSheet(cells, ctx, loaiPhi, xeList);
      if (kq.bo === 'tieude') continue;
      tong += 1;
      if (kq.bo === 'trong') { trong += 1; continue; }
      const k = khoaChang(kq.d);
      if ((kq.d.ngay && kq.d.container && kq.d.xe && keys.has(k)) || raws.has(kq.d.raw)) { daCo += 1; continue; }
      keys.add(k); raws.add(kq.d.raw);
      moi.push(kq.d);
    }
    const loi = moi.filter(d => kiemDong(d, daLuu, nhap.concat(moi), loaiPhi, ctx.homNay).loi).length;
    let bo = '';
    if (daCo) bo += ` · bỏ ${daCo} dòng đã có`;
    if (trong) bo += ` · bỏ ${trong} dòng trống`;
    return {
      drafts: moi, loi,
      cau: `Vừa dán ${tong} dòng: ${moi.length} dòng nháp${loi ? `, ${loi} dòng có ô đỏ cần sửa` : ''}${bo}`,
      ghi: `Vừa dán ${tong} dòng${bo}`,
    };
  }

  // Dòng nháp → một dòng của lệnh lưu chặng (POST /api/v7/doixe/chang).
  function dongGui(d) {
    const phi = {};
    for (const [ma, v] of Object.entries(d.phi)) if (v !== null && v !== undefined) phi[ma] = String(v);
    const chu = v => (v && String(v).trim() ? String(v).trim().slice(0, 200) : null);
    return {
      ngay: d.ngay || null, container: d.container, loai: d.loai, xe_id: d.xe, tai_xe_id: d.taiXe ?? null,
      tra: d.nguoiTra ? 'nguoi' : 'cong_ty', nguoi_tra_id: d.nguoiTra ?? null,
      noi_lay: chu(d.noi_lay), noi_ha: chu(d.noi_ha), kho: chu(d.kho), tinh: chu(d.tinh), ten_hang: chu(d.ten_hang), ghi_chu: chu(d.ghi_chu), phi,
      ...Object.fromEntries(Object.keys(SO_LUONG).map(k => [k, d[k] === null || d[k] === undefined ? null : String(d[k])])),
    };
  }

  const MA_LOI_MAY = {
    NGAY_TUONG_LAI: 'Ngày sau hôm nay', NGAY_THIEU: 'Thiếu ngày', CONT_THIEU: 'Thiếu cont', XE_KHONG_RO: 'Không rõ xe',
    TRUNG_CHANG: 'Đã có chặng này',
  };
  const COT_LOI_MAY = { ngay: 'ngay', container: 'container', xe_id: 'xe' };
  const loiMay = e => ({ cot: COT_LOI_MAY[e.cot] ?? 'container', ma: MA_LOI_MAY[e.ma] ?? e.ma });

  // ---- Chặng đã lưu (dạng GET) ----
  const tienDong = (dong, loaiPhi) => {
    let s = null;
    for (const ma of phiTien(loaiPhi)) if (dong.phi[ma] !== undefined) s = (s ?? 0) + so(dong.phi[ma]);
    return s;
  };
  // Giá trị đang hiệu lực của một loại phí ở chặng: dòng gốc + điều chỉnh + trừ lại; null khi không dòng nào có ô đó.
  function phiHieuLuc(chang, ma) {
    let s = null;
    for (const dong of chang.dong) if (dong.phi[ma] !== undefined) s = (s ?? 0) + so(dong.phi[ma]);
    return s;
  }
  const phiGoc = (chang, ma) => {
    const goc = chang.dong.find(d => d.loai === 'goc');
    return goc && goc.phi[ma] !== undefined ? so(goc.phi[ma]) : null;
  };
  const tienChang = (chang, loaiPhi) => {
    let s = null;
    for (const dong of chang.dong) { const t = tienDong(dong, loaiPhi); if (t !== null) s = (s ?? 0) + t; }
    return s;
  };
  const coPhi = chang => chang.dong.some(d => Object.keys(d.phi).length > 0);
  const daHoan = chang => chang.dong.some(d => d.dot_hoan_id !== null);
  const chuaNoi = chang => !chang.da_bo && chang.loai === 'hang' && !chang.chuyen;
  const laChuaHoan = (chang, nguoiId, loaiPhi) => !chang.da_bo && chang.nguoi_tra_id === nguoiId
    && chang.dong.some(d => d.dot_hoan_id === null && (tienDong(d, loaiPhi) ?? 0) !== 0);

  // Các dòng chờ hoàn của một người (mọi tháng), theo tháng rồi ngày.
  function dongChuaHoan(changs, nguoiId, loaiPhi) {
    const out = [];
    for (const c of changs) {
      if (c.nguoi_tra_id !== nguoiId) continue;
      for (const d of c.dong) {
        const t = tienDong(d, loaiPhi);
        if (d.dot_hoan_id === null && t !== null && t !== 0) out.push({ chang: c, dong: d, tien: t });
      }
    }
    return out.sort((a, b) => (a.chang.ngay < b.chang.ngay ? -1 : a.chang.ngay > b.chang.ngay ? 1 : a.dong.id - b.dong.id));
  }
  const tongTien = list => list.reduce((s, x) => s + x.tien, 0);
  // Đợt hoàn: tổng các dòng − số thực chuyển (dương là phần trừ vào tiền ứng đang giữ).
  const chenhDot = dot => so(dot.tong_dong_vnd) - so(dot.so_tien_vnd);
  // Khoản (ứng, tiền về) chưa hủy cùng ngày, cùng số tiền với khoản sắp ghi: hộp ghi cảnh báo trùng trước khi ghi (audit DX-03).
  const khoanTrung = (ds, ngay, tien) => (ds ?? []).find(x => !x.huy && x.ngay === ngay && so(x.so_tien_vnd) === tien) ?? null;
  // Tổng mọi khoản phí ở mọi dòng của chặng (cả phí công ty trả), như máy chủ so khi xóa chặng (audit DX-06). Không ô nào: 0.
  const tongPhiChang = c => c.dong.reduce((s, d) => Object.values(d.phi).reduce((t, v) => t + so(v), s), 0);
  const tongChon = (dongs, chon) => dongs.reduce((s, x) => s + (chon.has(x.dong.id) ? x.tien : 0), 0);

  // Hoàn khác tổng: âm là chuyển ít hơn (phần thiếu trừ vào tiền ứng đang giữ), dương là chuyển nhiều hơn (như ứng thêm).
  const lechHoan = (tien, tong) => tien - tong;
  const truUngGiu = soDu => Math.max(0, soDu);
  const sauKhiGhi = (soDu, tien) => soDu - tien;
  const sauKhiHuy = (soDu, tien) => soDu + tien;
  const cuoiThe = the => so(the.dau_vnd) + so(the.chi_vnd) - so(the.hoan_vnd) - so(the.ung_vnd);

  const loiDu = (v, ten) => (v > 0 ? `Công ty còn nợ ${fmt(v)}` : v < 0 ? `${ten} đang giữ ${fmt(-v)}` : 'Không còn nợ');
  const nhanCuoi = (v, ten) => (v > 0 ? `Công ty còn nợ ${ten}` : v < 0 ? `${ten} đang giữ tiền ứng` : 'Không còn nợ');

  // Cách xem Gọn: 5 loại phí dùng nhiều nhất trong tháng (luôn có Phí nâng và Nâng hạ); còn lại gom "Phí khác". VETC cột riêng.
  function cotPhiGon(changs, loaiPhi, toiDa) {
    const ds = loaiPhi.filter(p => !p.cong_ty_tra);
    const dem = Object.fromEntries(ds.map(p => [p.ma, 0]));
    for (const c of changs) for (const p of ds) if (c.dong.some(d => d.phi[p.ma] !== undefined)) dem[p.ma] += 1;
    const co = ds.filter(p => dem[p.ma] > 0 || p.ma === 'nang' || p.ma === 'nangha')
      .sort((a, b) => dem[b.ma] - dem[a.ma] || a.thu_tu - b.thu_tu);
    const giu = new Set(co.slice(0, toiDa).map(p => p.ma));
    return { hien: ds.filter(p => giu.has(p.ma)), khac: ds.filter(p => !giu.has(p.ma) && dem[p.ma] > 0) };
  }
  function phiKhac(chang, khac) {
    let s = null;
    const ct = [];
    for (const p of khac) {
      const v = phiHieuLuc(chang, p.ma);
      if (v !== null) { s = (s ?? 0) + v; ct.push(`${p.ten} ${fmt(v)}`); }
    }
    return { tong: s, chiTiet: ct.join(' · ') };
  }
  function phiKhacNhap(d, khac) {
    let s = null;
    for (const p of khac) if (d.phi[p.ma] !== undefined) s = (s ?? 0) + d.phi[p.ma];
    return s;
  }

  // Tổng cột của bảng: chỉ dòng của người đang mở (sổ người) hoặc mọi dòng (sổ xe); VETC cộng mọi dòng.
  function tongCot(changs, ma, nguoiId, laSoXe) {
    let s = null;
    for (const c of changs) {
      if (!laSoXe && ma !== 'vetc' && c.nguoi_tra_id !== nguoiId) continue;
      const v = phiHieuLuc(c, ma);
      if (v !== null) s = (s ?? 0) + v;
    }
    return s;
  }
  function tongChi(changs, loaiPhi, nguoiId, laSoXe) {
    let s = null;
    for (const c of changs) {
      if (!laSoXe && c.nguoi_tra_id !== nguoiId) continue;
      const v = tienChang(c, loaiPhi);
      if (v !== null) s = (s ?? 0) + v;
    }
    return s;
  }

  // Thẻ của sổ xe: tài xế chi, người đi lệnh chi, công ty trả VETC, tổng chi phí chặng.
  function theXe(changs, loaiPhi, nguoiList) {
    const vai = Object.fromEntries(nguoiList.map(n => [n.id, n.vai]));
    let tx = 0, dl = 0, vetc = 0, cty = 0;
    for (const c of changs) {
      const t = tienChang(c, loaiPhi) ?? 0;
      if (c.nguoi_tra_id === null) cty += t;
      else if (vai[c.nguoi_tra_id] === 'di_lenh') dl += t;
      else tx += t;
      for (const p of loaiPhi) if (p.cong_ty_tra) vetc += phiHieuLuc(c, p.ma) ?? 0;
    }
    const conLai = changs.filter(c => !c.da_bo);
    return { soChang: conLai.length, hang: conLai.filter(c => c.loai === 'hang').length, phu: conLai.filter(c => c.loai !== 'hang').length,
      tx, dl, cty, vetc, tong: tx + dl + cty + vetc };
  }

  // Thứ tự bảng Người nhận ứng: công ty nợ nhiều xếp đầu, rồi người giữ tiền ứng nhiều, rồi không còn nợ.
  function xepNguoi(rows) {
    return rows.slice().sort((a, b) => {
      const x = so(a.so_du_vnd), y = so(b.so_du_vnd);
      return (y > 0) - (x > 0) || (x > 0 ? y - x : x - y) || a.id - b.id;
    });
  }
  function tongNguoi(rows) {
    let no = 0, giu = 0, chuaHoan = 0;
    for (const r of rows) {
      const v = so(r.so_du_vnd);
      if (v > 0) no += v; else giu -= v;
      chuaHoan += r.chua_hoan;
    }
    return { no, giu, chuaHoan };
  }

  // ---- Lịch sử ----
  const tenNguoi = (id, nguoiList) => (id === null || id === undefined ? 'Công ty' : nguoiList.find(n => n.id === id)?.ten ?? `#${id}`);
  const giaTri = (cot, v, dm) => {
    if (v === null || v === undefined || v === '') return '—';
    if (cot === 'ngay') return ddmm(v);
    if (cot === 'loai') return TEN_LOAI[v] ?? v;
    if (cot === 'xe_id') return dm.xe.find(x => String(x.id) === String(v))?.bien_so ?? v;
    if (cot === 'nguoi_tra') return v === 'cong_ty' ? 'Công ty' : tenNguoi(Number(v), dm.nguoi);
    if (String(cot).startsWith('phi:')) return fmt(so(v));
    return String(v);
  };
  const TEN_COT = { ngay: 'Ngày', container: 'Container', loai: 'Loại chặng', xe_id: 'Xe', noi_lay: 'Nơi lấy', noi_ha: 'Nơi hạ', kho: 'Kho',
    ghi_chu: 'Ghi chú', ...Object.fromEntries(Object.entries(SO_LUONG).map(([k, sl]) => [k, sl.ten])) };
  const tenCot = (cot, loaiPhi) => (String(cot).startsWith('phi:') ? loaiPhi.find(p => p.ma === cot.slice(4))?.ten ?? cot : TEN_COT[cot] ?? cot);
  const LY_DC = { thang_khoa: 'Tháng đã khóa', da_hoan: 'Dòng đã hoàn', co_dieu_chinh: 'Đã có điều chỉnh' };

  function moTaSuKien(e, dm, loaiPhi) {
    const t = e.truoc ?? {}, s = e.sau ?? {};
    const ten = tenNguoi(e.nguoi_id, dm.nguoi);
    const du = v => (v === null || v === undefined ? '' : loiDu(so(v), ten));
    const chang = t.ngay ? `${ddmm(t.ngay)} · ${t.container}` : '';
    const out = { viec: '', chi: '', truoc: '', sau: '', lyDo: e.ly_do ?? '' };
    switch (e.viec) {
      case 'nap': Object.assign(out, { viec: 'Nạp danh mục', chi: `${s.so_nguoi} người · ${s.so_xe} xe` }); break;
      case 'them_chang': Object.assign(out, { viec: 'Thêm chặng', chi: `${s.so_dong} dòng (${ddmm(s.tu)}${s.den !== s.tu ? `–${ddmm(s.den)}` : ''}) · chi phí ${fmt(so(s.tien_vnd))}${s.sau_khoa ? ` · ${s.sau_khoa} dòng vào tháng đã khóa` : ''}` }); break;
      case 'sua_chang': Object.assign(out, { viec: 'Sửa ô', chi: `${tenCot(t.cot, loaiPhi)} · ${chang}`, truoc: giaTri(t.cot, t.gia_tri, dm), sau: giaTri(t.cot, s.gia_tri, dm) }); break;
      case 'dieu_chinh': Object.assign(out, { viec: 'Điều chỉnh', chi: `${LY_DC[s.ly_do_dc] ?? ''} · ${tenCot(t.cot, loaiPhi)} · ${chang}`,
        truoc: giaTri(t.cot, t.gia_tri, dm), sau: `${giaTri(t.cot, s.gia_tri, dm)} (thêm dòng ${fmtDau(so(s.chenh_vnd))})` }); break;
      case 'doi_nguoi_tra': Object.assign(out, { viec: 'Đổi người trả', chi: chang, truoc: giaTri('nguoi_tra', t.nguoi_tra, dm), sau: giaTri('nguoi_tra', s.nguoi_tra, dm) }); break;
      case 'xoa_chang': Object.assign(out, { viec: 'Xóa chặng', chi: chang, truoc: `Chi ${fmt(so(t.tien_vnd) ?? 0)}`, sau: 'đã xóa' }); break;
      case 'bo_chang': Object.assign(out, { viec: 'Bỏ chặng', chi: `${LY_DC[s.ly_do_dc] ?? ''} · ${chang}`, truoc: `Chi ${fmt(so(t.tien_vnd) ?? 0)}`, sau: 'thêm dòng trừ lại' }); break;
      case 'ghi_ung': Object.assign(out, { viec: 'Ghi ứng', chi: `${fmt(so(s.so_tien_vnd))} · chuyển ngày ${ddmm(s.ngay)}${s.ghi_chu ? ` · ${s.ghi_chu}` : ''}`, truoc: du(t.so_du_vnd), sau: du(s.so_du_vnd) }); break;
      case 'huy_ung': Object.assign(out, { viec: 'Hủy lần ứng', chi: `${ddmm(t.ngay)} · ${fmt(so(t.so_tien_vnd))}`, truoc: du(t.so_du_vnd), sau: du(s.so_du_vnd) }); break;
      case 'ghi_hoan': {
        const lech = so(s.tong_dong_vnd) - so(s.so_tien_vnd);
        Object.assign(out, { viec: 'Ghi đợt hoàn', chi: `${s.so_dong} dòng ${fmt(so(s.tong_dong_vnd))}${lech > 0 ? ` · trừ ứng ${fmt(lech)}` : ''} · chuyển ${fmt(so(s.so_tien_vnd))} ngày ${ddmm(s.ngay)}`, truoc: du(t.so_du_vnd), sau: du(s.so_du_vnd) });
        break;
      }
      case 'huy_hoan': Object.assign(out, { viec: 'Hủy đợt hoàn', chi: `${ddmm(t.ngay)} · ${fmt(so(t.so_tien_vnd))} · ${s.dong_tro_lai} dòng trở lại Chưa hoàn`, truoc: du(t.so_du_vnd), sau: du(s.so_du_vnd) }); break;
      case 'khoa_thang': Object.assign(out, { viec: `${s.khoa ? 'Khóa' : 'Mở khóa'} tháng ${Number(String(s.thang).slice(5, 7))}/${String(s.thang).slice(0, 4)}`, chi: 'Cả đội xe', truoc: t.khoa ? 'Đã khóa' : 'Đang mở', sau: s.khoa ? 'Đã khóa' : 'Đang mở' }); break;
      default: out.viec = e.viec;
    }
    return out;
  }

  return {
    LOAI, TEN_LOAI, COT, SO_LUONG, docSoLuong, ganSoLuong, gioMay, kmTinh, so, fmt, fmtDau, ddmm, ddmmyyyy, thangCua, boDau, chuSo, docSo, docTien, docNgaySheet, docNgayGo, docNgayApGia, ngayApMacDinh, cacThang, chuanCont,
    tachTSV, doanLoai, timXe, dongTuSheet, hoanThien, nhapTuGo, moiCo, khoaChang, khoaDaLuu, chiNhap, kiemDong, danKhoi, dongGui, loiMay,
    tienDong, phiHieuLuc, phiGoc, tienChang, coPhi, daHoan, chuaNoi, laChuaHoan, dongChuaHoan, tongTien, chenhDot, tongPhiChang, khoanTrung, tongChon, lechHoan, truUngGiu, sauKhiGhi,
    sauKhiHuy, cuoiThe, loiDu, nhanCuoi, cotPhiGon, phiKhac, phiKhacNhap, tongCot, tongChi, theXe, xepNguoi, tongNguoi, tenNguoi, tenCot,
    moTaSuKien,
  };
}));
