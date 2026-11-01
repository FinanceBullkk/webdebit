/* Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): khối "Từ Sheet chờ đưa vào sổ" của tab Việc cần làm.
   Đọc GET /api/v7/inbox (API tính nền việc hàng chờ của mọi sổ). Chỉ đọc: mỗi dòng mở đúng sổ, việc làm ở sổ như cũ. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InboxCard = api;
}(typeof self !== 'undefined' ? self : this, function () {
  const ROWS = 8;   // mỗi nhóm hiện 8 sổ đầu, phần còn lại gập trong "Xem thêm"
  const REASONS = { OTHER_BOOK_LEGACY: 'đã có ở sổ khác', OTHER_CUSTOMER: 'container đang ở khách khác',
    CONTAINER_REUSED_OR_CHANGED: 'container đã dùng', AMBIGUOUS_MATCH: 'nhiều chuyến trùng', FIELDS: 'Sheet đổi ngày/booking' };
  const big = value => BigInt(/^-?\d+$/.test(String(value ?? '')) ? value : 0);
  const clock = iso => new Date(iso).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });

  // Các nhóm theo thứ tự đụng tiền: mỗi nhóm có hàm đếm, câu cho từng sổ và số tiền để xếp.
  const GROUPS = [
    { key: 'receipts', title: 'Phiếu thu từ Sheet chờ ghi', tone: 'warning', unit: 'phiếu',
      count: b => b.receipts.ready + b.receipts.review, money: b => b.receipts.amount_vnd,
      what: (b, F) => `${b.receipts.ready + b.receipts.review} phiếu · ${F.short(b.receipts.amount_vnd)}${b.receipts.review ? ` (${b.receipts.review} cần xem)` : ''}` },
    { key: 'removed', title: 'Chuyến đang tính nợ nhưng không còn trên Sheet', tone: 'critical', unit: 'chuyến',
      count: b => b.removed.count, money: b => b.removed.amount_vnd,
      what: (b, F) => `${b.removed.count} chuyến · ${F.short(b.removed.amount_vnd)}` },
    { key: 'trips_new', title: 'Chuyến mới từ Sheet chờ duyệt', tone: 'neutral', unit: 'chuyến',
      count: b => b.trips_new, what: b => `${b.trips_new} chuyến` },
    { key: 'trips_check', title: 'Chuyến cần người xem', tone: 'warning', unit: 'chuyến',
      count: b => b.trips_check.count,
      what: b => `${b.trips_check.count} chuyến · ${Object.entries(b.trips_check.reasons).sort((x, y) => y[1] - x[1])
        .map(([reason, n]) => `${n} ${REASONS[reason] ?? 'cần xem'}`).join(', ')}` },
    { key: 'prices', title: 'Giá từ Sheet', tone: 'neutral', unit: 'giá',
      count: b => b.prices.ready + b.prices.review,
      what: b => [b.prices.ready && `${b.prices.ready} sẵn sàng ghi`, b.prices.review && `${b.prices.review} cần xem`].filter(Boolean).join(' · ') },
    { key: 'ps', title: 'Phụ phí PS cần xem', tone: 'neutral', unit: 'dòng',
      count: b => b.ps.ready + b.ps.review,
      what: b => [b.ps.ready && `${b.ps.ready} sẵn sàng tách`, b.ps.review && `${b.ps.review} cần xem`].filter(Boolean).join(' · ') },
  ];

  function rows(books, group, F, esc, label, href) {
    const sorted = books.filter(b => group.count(b) > 0)
      .sort((x, y) => (group.money ? Number(big(group.money(y)) - big(group.money(x))) : 0) || group.count(y) - group.count(x)
        || label(x).localeCompare(label(y), 'vi'));
    const item = b => `<li><a href="${href(b.customer_id)}"><span class="who">${esc(label(b))}</span><span class="what">${esc(group.what(b, F))}</span><span class="chev" aria-hidden="true">›</span></a></li>`;
    const head = sorted.slice(0, ROWS).map(item).join('');
    const more = sorted.slice(ROWS);
    return { sorted, html: `<ul class="rows">${head}</ul>${more.length ? `<details class="more"><summary>Xem thêm ${more.length} sổ</summary><ul class="rows">${more.map(item).join('')}</ul></details>` : ''}` };
  }

  // data: kết quả GET /api/v7/inbox (hoặc null khi lỗi tải); label(book) → tên khách; href(id) → địa chỉ sổ.
  function render(data, { F, esc, label, href, failedText }) {
    const head = aside => `<div class="card-head"><h2 id="h-inbox">Từ Sheet chờ đưa vào sổ</h2>${aside ? `<span class="aside">${aside}</span>` : ''}</div>`;
    const card = (aside, body) => `<section class="card inbox" aria-labelledby="h-inbox">${head(aside)}${body}</section>`;
    if (!data) return card('', `<p class="empty inbox-error">${esc(failedText)} <button type="button" class="btn" data-inbox-retry>Thử lại</button></p>`);
    if (data.state === 'unavailable') {
      return card('', '<p class="empty">Chưa đọc được bản lấy từ Sheet nên chưa tính được việc. Bấm "Làm mới" để lấy lại từ Sheet.</p>');
    }
    if (data.state === 'computing') {
      const progress = data.books_total ? ` (đã xong ${data.books_done}/${data.books_total} sổ)` : '';
      return card('', `<p class="empty loading">Đang tính việc của mọi sổ${progress}… khoảng 2 phút.</p>`);
    }
    const when = [data.computed_at && `Tính lúc ${clock(data.computed_at)}`, data.sheet_at && `Sheet lúc ${clock(data.sheet_at)}`]
      .filter(Boolean).join(' · ');
    const aside = esc(when) + (data.refreshing ? ' · đang cập nhật…' : '');
    const books = data.books ?? [];
    const failed = (data.failed ?? []).length
      ? `<p class="inbox-note warn">${data.failed.length} sổ chưa tính được, việc của các sổ này có thể thiếu.</p>` : '';
    const groups = GROUPS.map(group => ({ group, ...rows(books, group, F, esc, label, href) })).filter(part => part.sorted.length);
    const textBooks = books.filter(b => b.text_diff > 0);
    const textCount = textBooks.reduce((sum, b) => sum + b.text_diff, 0);
    if (!groups.length && !textCount) return card(aside, `${failed}<p class="empty">Không còn việc từ Sheet.</p>`);
    const total = groups.reduce((sum, part) => sum + part.sorted.reduce((n, b) => n + part.group.count(b), 0), 0);
    const money = books.reduce((sum, b) => sum + big(b.receipts.amount_vnd), 0n);
    const bookCount = new Set(groups.flatMap(part => part.sorted.map(b => b.customer_id))).size;
    const summary = total ? `<p class="inbox-summary">Còn <b>${total}</b> việc ở <b>${bookCount}</b> sổ${money ? ` · phiếu thu chờ ghi <b>${esc(F.short(money.toString()))}</b>` : ''}</p>` : '';
    const body = groups.map(({ group, sorted, html }) => {
      const n = sorted.reduce((sum, b) => sum + group.count(b), 0);
      return `<div class="todo-group" data-group="${group.key}"><div class="todo-title"><span>${group.title}</span><span class="tag ${group.tone}">${n} ${group.unit}</span></div>${html}</div>`;
    }).join('');
    const text = textCount ? `<p class="inbox-note">Lệch chữ nơi đi, nơi đến, shipper: ${textCount} chỗ ở ${textBooks.length} sổ. Không đụng tiền; sắp tới máy tự lấy theo Sheet.</p>` : '';
    return card(aside, `${summary}${failed}${body}${text}`);
  }

  return { render, GROUPS, REASONS };
}));
