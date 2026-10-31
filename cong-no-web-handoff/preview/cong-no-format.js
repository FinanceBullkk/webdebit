/* Định dạng tiền và chuỗi dùng chung cho mọi trang V7 (Tổng quan, Việc cần làm, Công nợ theo tháng, sổ khách, Đòi nợ,
   Chat Zalo, hàng chờ Sheet). Tiền từ API là chuỗi số nguyên VND; mọi phép tính ở đây dùng BigInt, không qua số thực
   (ARCH-03: trang chỉ gọi hàm, không tự cộng trừ tiền). Trang nạp file này trước mọi script khác rồi destructure hàm
   cần dùng; không chép lại helper trong file trang (gom 31/10/2026). */
const CongNoFormat = (() => {
  'use strict';
  const BILLION = 1000000000n;
  const MILLION = 1000000n;

  function toBig(value) {
    if (typeof value === 'bigint') return value;
    if (typeof value !== 'string' || !/^-?[0-9]+$/.test(value)) throw Error('Dữ liệu tiền từ API không hợp lệ.');
    return BigInt(value);
  }

  const abs = value => (value < 0n ? -value : value);
  const sign = value => (value < 0n ? '−' : '');

  // Làm tròn nửa lên |value| / unit tới `digits` chữ số thập phân, bỏ số 0 thừa: "6,42", "11,8", "9".
  function scaled(value, unit, digits) {
    const factor = 10n ** BigInt(digits);
    const rounded = (value * factor * 2n + unit) / (unit * 2n);
    const whole = (rounded / factor).toLocaleString('vi-VN');
    const fraction = (rounded % factor).toString().padStart(digits, '0').replace(/0+$/, '');
    return fraction ? `${whole},${fraction}` : whole;
  }

  /** Số đồng đầy đủ: "21.790.000.000 đ"; số âm dùng dấu trừ "−". */
  function full(value) {
    const amount = toBig(value);
    return `${sign(amount)}${abs(amount).toLocaleString('vi-VN')} đ`;
  }

  /** Rút gọn để đọc nhanh: "63,91 tỷ", "350 triệu", "950.000 đ". `unit` là chữ cho triệu ("triệu" hoặc "tr"). */
  function short(value, unit = 'triệu') {
    const amount = toBig(value);
    const size = abs(amount);
    // 999,95 triệu trở lên làm tròn ra "1.000 triệu" — đọc là tỷ cho tự nhiên.
    if (size >= BILLION - 50000n) return `${sign(amount)}${scaled(size, BILLION, 2)} tỷ`;
    if (size >= MILLION) return `${sign(amount)}${scaled(size, MILLION, 1)} ${unit}`;
    return full(amount);
  }

  /** Cột tiền theo tỷ, luôn 2 số lẻ để mắt so được theo cột: "21,79", "0,97", "0,07". */
  function billions(value) {
    const amount = toBig(value);
    const rounded = (abs(amount) * 200n + BILLION) / (BILLION * 2n);
    return `${sign(amount)}${(rounded / 100n).toLocaleString('vi-VN')},${(rounded % 100n).toString().padStart(2, '0')}`;
  }

  /** Tỉ lệ phần trăm một chữ số thập phân: "34,1%". Tổng không dương thì không có tỉ lệ. */
  function percent(part, total) {
    const whole = toBig(total);
    if (whole <= 0n) return '—';
    const amount = toBig(part);
    return `${sign(amount)}${scaled(abs(amount) * 100n, whole, 1)}%`;
  }

  /** Tỉ lệ dùng cho độ rộng thanh (CSS %), làm tròn 0,1; không âm, tối đa 100. */
  function barWidth(part, total) {
    const whole = toBig(total);
    const amount = toBig(part);
    if (whole <= 0n || amount <= 0n) return 0;
    const perMille = (amount * 2000n + whole) / (whole * 2n);
    return Number(perMille > 1000n ? 1000n : perMille) / 10;
  }

  /** Cộng một danh sách tiền (chuỗi hoặc BigInt). */
  function sum(values) {
    return values.reduce((total, value) => total + toBig(value), 0n);
  }

  /** Bậc màu 1–6 theo số tiền tuyệt đối (200 triệu, 500 triệu, 1 tỷ, 2 tỷ, 4 tỷ) để màu không đổi khi lọc. */
  function heatStep(value) {
    const amount = toBig(value);
    return [200n * MILLION, 500n * MILLION, BILLION, 2n * BILLION, 4n * BILLION].filter(step => amount >= step).length + 1;
  }

  // ---- Chuỗi dùng chung (31/10/2026): trước đó mỗi trang chép một bản esc/fold/nhãn; gom về đây, trang chỉ destructure. ----
  const UNSORTED = 'Chưa phân loại';

  /** Thoát HTML cho chuỗi chèn vào innerHTML (& < > " '); null/undefined thành chuỗi rỗng. */
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);

  /** Bỏ dấu tiếng Việt và hạ chữ thường, giữ nguyên dấu câu, khoảng trắng và độ dài ("Hoàng" → "hoang", "đ" → "d");
   *  cùng quy tắc với `fold` của web/v7_zalo_chat.py nên tô đúng vị trí khớp trong tin nhắn. */
  const foldText = value => String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();

  /** Khóa tìm kiếm (MH-01): như foldText, rồi gộp mọi ký tự ngoài a–z/0–9 thành một khoảng trắng và cắt hai đầu —
   *  gõ "sau rieng bo" khớp "Sầu riêng · bộ". */
  const fold = value => foldText(value).replace(/[^a-z0-9]+/g, ' ').trim();

  /** Phương thức vận chuyển: CANG → "cảng", BO → "bộ" (DB chỉ có hai mã này); mã lạ hạ chữ thường, trống → "". */
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? (mode ? String(mode).toLowerCase() : '');

  /** Nhãn mặt hàng kèm phương thức "Sầu riêng · bộ"; không có phương thức thì chỉ mặt hàng; thiếu mặt hàng → "Chưa phân loại". */
  const commodityText = (commodity, mode) => commodity ? `${commodity}${transportText(mode) ? ` · ${transportText(mode)}` : ''}` : UNSORTED;

  /** Tên sổ khách: `label` server đặt sẵn nếu có; không thì tên Sheet (display_name, rồi name) kèm " · mặt hàng · phương thức" khi sổ có mặt hàng. */
  const customerLabel = row => row.label || `${row.display_name ?? row.name}${row.commodity ? ` · ${commodityText(row.commodity, row.transport_mode)}` : ''}`;

  /** Map String(id) → nhãn duy nhất trong danh sách: sổ trùng nhãn thêm " · sổ <id>". Khóa là chuỗi để tra được từ URL lẫn JSON. */
  function customerLabels(rows) {
    const counts = new Map();
    for (const row of rows) counts.set(customerLabel(row), (counts.get(customerLabel(row)) ?? 0) + 1);
    return new Map(rows.map(row => {
      const label = customerLabel(row);
      return [String(row.id), counts.get(label) > 1 ? `${label} · sổ ${row.id}` : label];
    }));
  }

  // Ba cách ghi tháng đang dùng trên các trang; `iso` là khóa "YYYY-MM" hoặc ngày "YYYY-MM-DD", chỉ đọc 7 ký tự đầu.
  /** Dạng ngắn "7/2026" (sổ khách, Tổng quan). */
  const monthLabel = iso => `${Number(iso.slice(5, 7))}/${iso.slice(0, 4)}`;
  /** Dạng đầy đủ "Tháng 07/2026" (tab Đòi nợ). */
  const monthTitle = iso => `Tháng ${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  /** Thẻ "T7", kèm năm "T12/2025" khi khác `year` (Công nợ theo tháng). */
  const monthTag = (iso, year) => `T${Number(iso.slice(5, 7))}${Number(iso.slice(0, 4)) === year ? '' : `/${iso.slice(0, 4)}`}`;

  return { toBig, full, short, billions, percent, barWidth, sum, heatStep,
    UNSORTED, esc, foldText, fold, transportText, commodityText, customerLabel, customerLabels, monthLabel, monthTitle, monthTag };
})();
if (typeof module !== 'undefined') module.exports = CongNoFormat;
