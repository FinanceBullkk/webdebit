/* BAO-CAO-THANG-01: phần tính của trang Báo cáo tháng (ARCH-03: file -ui.js chỉ vẽ). Số đếm do API tính sẵn
 * (GET /api/v7/report/month); ở đây chỉ đặt chữ nghiệp vụ, lọc khách và dựng các hàng của bảng tổng. Không cộng tiền. */
const BaoCaoThangModel = (() => {
  'use strict';
  const FAMILY = { BIEN: 'Biển', BO: 'Bộ' };
  const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

  // Trạng thái một chuyến → chữ người dùng quen và mức màu (ok, warn, bad, muted).
  function statusOf(row, current = false) {
    const web = Boolean(row.web);
    switch (row.status) {
      case 'khop': return web ? { text: 'Khớp', tone: 'ok' } : { text: 'Web chưa có', tone: 'warn' };
      case 'lech_ngay': return { text: `Lệch ngày ${dayGap(row.date, row.booking?.date)}`, tone: 'warn' };
      case 'thieu': {   // BAO-CAO-THANG-02: nói rõ web đã có chưa, vì máy đưa chuyến booking vào web trước khi Sheet ghi
        const sheet = current ? 'Chưa lên Sheet' : 'Sheet chưa ghi';
        return web ? { text: sheet, tone: current ? 'warn' : 'bad' } : { text: `${sheet}, web chưa có`, tone: 'bad' };
      }
      case 'khong_booking': return { text: 'Booking không có', tone: 'bad' };
      case 'khong_ngay': return { text: 'Sheet không ghi ngày', tone: 'warn' };
      case 'chep': return { text: 'Dòng chép 0đ', tone: 'muted' };
      case 'ngoai': return { text: 'Không thuộc biển/bộ', tone: 'muted' };
      case 'chi_web': return { text: 'Chỉ có trên web', tone: 'bad' };
      default: return { text: String(row.status ?? ''), tone: 'muted' };
    }
  }

  function dayGap(a, b) {
    if (!a || !b) return '';
    const gap = Math.round(Math.abs(Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / 86400000);
    return `${gap} ngày`;
  }

  // Ô "Cần xem" của một khách: mỗi loại lệch một chip, thứ tự theo mức đụng tiền. Bản chép 0đ chỉ để biết.
  function chips(customer, current = false) {
    const out = [];
    const add = (count, text, tone) => { if (count) out.push({ text: `${text} ${count}`, tone }); };
    add(customer.thieu, current ? 'Chưa lên Sheet' : 'Sheet chưa ghi', current ? 'warn' : 'bad');
    add(customer.khong_booking, 'Booking không có', 'bad');
    add(customer.chi_web, 'Chỉ trên web', 'bad');
    add((customer.web_thieu ?? 0) + (customer.thieu_web ?? 0), 'Web chưa có', 'warn');
    add(customer.lech_ngay, 'Lệch ngày', 'warn');
    add(customer.khong_ngay, 'Không ngày', 'warn');
    add(customer.chep, 'Chép 0đ', 'muted');
    return out;
  }

  const familyText = families => (families?.length ? families.map(family => FAMILY[family] ?? family).join(', ') : '—');

  function filter(customers, { onlyIssues = false, family = null } = {}) {
    return (customers ?? []).filter(item => (!onlyIssues || item.issues > 0) && (!family || (item.families ?? []).includes(family)));
  }

  // Bảng tổng trên cùng: mỗi hàng ba ô Biển, Bộ, Tổng; null là chưa có số (hiện "—", không như 0).
  function summaryRows(totals, current = false) {
    const pick = key => ['BIEN', 'BO', 'ALL'].map(family => totals?.[family]?.[key] ?? null);
    return [
      { key: 'booking', label: 'Booking có', values: pick('booking') },
      { key: 'sheet', label: 'Sheet sổ nợ đã ghi', values: pick('sheet') },
      { key: 'web', label: 'Web đã ghi', values: pick('web') },
      { key: 'thieu', label: current ? 'Booking có, chưa lên Sheet' : 'Booking có, Sheet chưa ghi', values: pick('thieu'), flag: true },
      { key: 'web_chua', label: 'Booking có, web chưa có', values: pick('web_chua'), flag: true, list: true },
      { key: 'web_thieu', label: 'Sheet có, web chưa có', values: pick('web_thieu'), flag: true },
    ];
  }

  // BAO-CAO-THANG-02: lý do máy chưa đưa chuyến booking vào sổ web (mã từ GET /api/v7/report/month/missing) → câu cho người đọc
  // và việc phải làm: `sheet` tự hết khi Sheet ghi chuyến, `person` cần người, `machine` máy tự làm ở lượt sau, `book` xem trong sổ.
  const REASONS = {
    // WEB-CHINH-01: Sheet sổ nợ đứng yên từ 1/12/2026. Từ 10/2026 máy đếm số dòng booking của container (DU-CHUYEN-01): booking không có
    // thêm dòng thì là cùng chuyến sổ đã tính ở ngày khác; là chuyến khác thật thì người nhập tay trong sổ.
    CONTAINER_REUSED_OR_CHANGED: ['Sổ đã có container này ở ngày khác, booking không có thêm dòng: máy coi là cùng chuyến. Nếu là chuyến khác, nhập tay trong sổ', 'book'],
    NO_BOOK: ['Tên chủ hàng chưa gắn sổ web (khách mới hoặc tên khác)', 'person'],
    COMMODITY_MISMATCH: ['Mặt hàng trên booking khác mặt hàng của sổ', 'person'],
    COMMODITY_UNKNOWN: ['Booking chưa ghi mặt hàng', 'person'],
    ROAD_BOOK: ['Tên trên booking biển trùng một sổ đường bộ', 'person'],
    // WEB-CHINH-01: Sheet sổ nợ thôi dùng từ 1/12/2026 nên ba ca chuyến bộ dưới không tự hết nữa; người gán tên hoặc chọn sổ trên web.
    ROAD_NO_TAB: ['Chủ hàng chưa gắn sổ web: gán tên chủ hàng cho sổ ở thẻ Khách (Quản trị)', 'person'],
    ROAD_TAB_FAR: ['Tab khách có dòng cùng container nhưng lệch ngày: chọn sổ ở Sổ khách hoặc Việc cần làm', 'person'],
    ROAD_AMBIGUOUS_TAB: ['Nhiều tab khách cùng ghi container này: chọn sổ ở Sổ khách hoặc Việc cần làm', 'person'],
    ROAD_NO_BOOK: ['Tab khách ghi chuyến này chưa có sổ web', 'person'],
    ROAD_AMBIGUOUS_SOURCE: ['Booking bộ ghi container này hai lần', 'person'],
    ROAD_EARLY: ['Trước tháng 10/2026: chuyến bộ đã tính theo sổ gốc', 'book'],
    NEEDS_REVIEW: ['Khác thông tin với sổ, cần người xem', 'person'],
    MONTH_LOCKED: ['Tháng đã khóa, cần người duyệt', 'person'],
    NEXT_RUN: ['Đủ điều kiện; máy đưa vào ở lượt tới', 'machine'],
    IN_BOOK_OTHER_DATE: ['Sổ đã có chuyến này ở ngày khác', 'book'],
    FUTURE: ['Ngày chuyến sau hôm nay', 'machine'],
    NOT_IN_SOURCE: ['Không còn trong bản chụp booking mới nhất', 'machine'],
    SOURCE_INCOMPLETE: ['Dòng booking thiếu thông tin', 'sheet'],
  };
  const WHO = { sheet: 'Tự hết khi Sheet ghi', person: 'Cần người', machine: 'Máy tự làm', book: 'Xem trong sổ' };

  function reasonOf(code) {
    const [text, who] = REASONS[code] ?? ['Chưa đọc được lý do', null];
    return { text, who, whoText: who ? WHO[who] : '—' };
  }

  // Các tháng chọn được: từ tháng đầu báo cáo tới tháng hiện tại, mới nhất trước.
  function months(start, end) {
    if (!MONTH.test(start ?? '') || !MONTH.test(end ?? '') || start > end) return MONTH.test(end ?? '') ? [end] : [];
    const out = [];
    for (let month = end; month >= start; month = shift(month, -1)) out.push(month);
    return out;
  }

  function shift(month, delta) {
    const [year, mon] = month.split('-').map(Number);
    const index = year * 12 + (mon - 1) + delta;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
  }

  const customerKey = item => `${item.book_id ?? ''}|${item.name ?? ''}|${item.owner ?? ''}`;

  return { statusOf, chips, familyText, filter, summaryRows, reasonOf, months, shift, customerKey, MONTH };
})();
if (typeof module !== 'undefined') module.exports = BaoCaoThangModel;
