/* Định dạng và cộng tiền dùng chung cho Tổng quan và Công nợ theo tháng.
   Tiền từ API là chuỗi số nguyên VND; mọi phép tính ở đây dùng BigInt, không qua số thực
   (ARCH-03: trang chỉ gọi hàm, không tự cộng trừ tiền). */
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

  return { toBig, full, short, billions, percent, barWidth, sum, heatStep };
})();
if (typeof module !== 'undefined') module.exports = CongNoFormat;
