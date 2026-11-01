/* Hộp ngoại lệ (specs/v7-hop-ngoai-le-p1.md, -p2.md): khối "Từ Sheet chờ đưa vào sổ" của tab Việc cần làm.
   Đọc GET /api/v7/inbox (API tính nền việc hàng chờ của mọi sổ). Mỗi dòng mở đúng sổ. Từ P2 nhóm phiếu thu ghi được
   ngay tại hộp: chọn sổ → xem lại nợ trước/sau → ghi bằng lệnh duyệt đang có của từng sổ (viec-can-lam.js gửi lệnh). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InboxCard = api;
}(typeof self !== 'undefined' ? self : this, function () {
  const ROWS = 8;   // mỗi nhóm hiện 8 sổ đầu, phần còn lại gập trong "Xem thêm"
  const REASONS = { OTHER_BOOK_LEGACY: 'đã có ở sổ khác', OTHER_CUSTOMER: 'container đang ở khách khác',
    CONTAINER_REUSED_OR_CHANGED: 'container đã dùng', AMBIGUOUS_MATCH: 'nhiều chuyến trùng', FIELDS: 'Sheet đổi ngày/booking' };
  const big = value => BigInt(/^-?\d+$/.test(String(value ?? '')) ? value : 0);
  const RECEIPT_REASONS = { NO_DATE: 'không rõ ngày', FUTURE_DATE: 'ngày sau hôm nay', SHEET_EDITED: 'Sheet sửa dòng sổ gốc',
    WEB_DELETED: 'đã xóa trên web' };
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

  // Sổ ghi được phiếu tại hộp: có phiếu sẵn sàng và đủ phiên bản sổ, bản chụp để gửi lệnh duyệt.
  const canWrite = b => b.receipts.ready > 0 && Number.isInteger(b.version) && /^[0-9a-f]{64}$/.test(b.receipts.snapshot_sha256 ?? '');
  const monthShort = key => `T${Number(String(key).slice(5, 7))}`;
  const dayText = iso => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '—');

  // Bước xem lại một sổ: nợ trước → sau (tạm tính, số thật lấy lại sau khi ghi), khách dư, tháng khóa.
  function reviewLine(b, F) {
    const total = big(b.receipts.ready_amount_vnd);
    const known = /^-?\d+$/.test(String(b.outstanding_vnd ?? ''));
    const before = known ? big(b.outstanding_vnd) : null;
    const after = known ? before - total : null;
    const notes = [];
    if (after !== null && after < 0n) notes.push(`khách sẽ dư ${F.short((-after).toString())}`);
    if ((b.receipts.locked_months ?? []).length) {
      notes.push(`có phiếu ngày trong tháng đang khóa (${b.receipts.locked_months.map(monthShort).join(', ')}): vẫn ghi được`);
    }
    return { count: b.receipts.ready, total: total.toString(), before: known ? before.toString() : null,
      after: after === null ? null : after.toString(), notes };
  }

  function receiptRows(books, F, esc, label, href, opts) {
    const selected = opts.selected ?? new Set();
    const sorted = books.filter(b => b.receipts.ready + b.receipts.review > 0)
      .sort((x, y) => Number(big(y.receipts.amount_vnd) - big(x.receipts.amount_vnd)) || label(x).localeCompare(label(y), 'vi'));
    const item = b => {
      const writable = canWrite(b);
      const failed = opts.result?.books?.find(row => row.customer_id === b.customer_id && !row.ok);
      const items = (b.receipts.items ?? []).map(row => `<li class="${row.status === 'READY' ? '' : 'muted'}">${esc(dayText(row.date))} · <b class="money">${esc(F.full(row.amount_vnd))}</b>`
        + `${row.note ? ` · ${esc(row.note)}` : ''}${row.status === 'READY' ? '' : ` · <i>cần xem: ${esc(RECEIPT_REASONS[row.status] ?? 'cần xem')}</i>`}</li>`).join('');
      const pick = writable
        ? `<label class="pick"><input type="checkbox" data-pick="${b.customer_id}"${selected.has(b.customer_id) ? ' checked' : ''}${opts.busy ? ' disabled' : ''}><span class="who">${esc(label(b))}</span></label>`
        : `<span class="who">${esc(label(b))}</span>`;
      return `<li class="receipt-book" data-book="${b.customer_id}"><div class="receipt-line">${pick}`
        + `<span class="what">${esc(GROUPS[0].what(b, F))}</span><a class="open" href="${href(b.customer_id)}">Mở sổ</a></div>`
        + `<details class="receipt-items"><summary>Xem phiếu</summary><ul>${items}</ul></details>`
        + `${failed ? `<p class="row-error" role="alert">${esc(failed.message)}</p>` : ''}</li>`;
    };
    const head = sorted.slice(0, ROWS).map(item).join('');
    const more = sorted.slice(ROWS);
    const writable = sorted.filter(canWrite);
    const picked = writable.filter(b => selected.has(b.customer_id));
    const sum = picked.reduce((total, b) => total + big(b.receipts.ready_amount_vnd), 0n);
    const bar = writable.length
      ? `<div class="receipt-bar"><label class="pick"><input type="checkbox" data-pick-all${picked.length === writable.length ? ' checked' : ''}${opts.busy ? ' disabled' : ''}> Chọn tất cả ${writable.length} sổ ghi được</label>`
        + `<button type="button" class="btn primary" data-review${picked.length && !opts.busy ? '' : ' disabled'}>Xem lại ${picked.length} sổ${picked.length ? ` (tổng ${esc(F.short(sum.toString()))})` : ''}</button></div>`
      : '';
    const moreHtml = more.length ? `<details class="more"><summary>Xem thêm ${more.length} sổ</summary><ul class="rows receipt-rows">${more.map(item).join('')}</ul></details>` : '';
    return { sorted, html: `<ul class="rows receipt-rows">${head}</ul>${moreHtml}${bar}` };
  }

  function reviewHtml(books, F, esc, label, busy) {
    const lines = books.map(b => ({ b, line: reviewLine(b, F) }));
    const count = lines.reduce((n, { line }) => n + line.count, 0);
    const total = lines.reduce((sum, { line }) => sum + big(line.total), 0n);
    const rowsHtml = lines.map(({ b, line }) => `<tr><td>${esc(label(b))}</td><td class="num">${line.count}</td><td class="num money">${esc(F.full(line.total))}</td>`
      + `<td class="num money">${line.before === null ? '—' : `${esc(F.full(line.before))} → <b>${esc(F.full(line.after))}</b>`}</td>`
      + `<td>${line.notes.map(note => `<span class="tag warning">${esc(note)}</span>`).join(' ')}</td></tr>`).join('');
    return `<div class="receipt-review" role="dialog" aria-labelledby="h-review"><h3 id="h-review">Xem lại trước khi ghi ${count} phiếu ở ${books.length} sổ · tổng ${esc(F.full(total.toString()))}</h3>`
      + `<table><thead><tr><th>Khách</th><th class="num">Phiếu</th><th class="num">Tổng phiếu</th><th class="num">Còn nợ trước → sau (tạm tính)</th><th>Lưu ý</th></tr></thead><tbody>${rowsHtml}</tbody></table>`
      + '<p class="tiny">Phiếu ghi đúng ngày trên Sheet, trừ vào nợ cũ trước. Ghi nhầm thì mở sổ để hủy phiếu (cần lý do).</p>'
      + `<div class="actions"><button type="button" class="btn primary" data-write${busy ? ' disabled' : ''}>${busy ? 'Đang ghi…' : `Ghi ${count} phiếu`}</button>`
      + `<button type="button" class="btn" data-review-cancel${busy ? ' disabled' : ''}>Thôi</button></div></div>`;
  }

  function resultHtml(result, F, esc, label, href) {
    if (!result) return '';
    const ok = result.books.filter(row => row.ok);
    const bad = result.books.filter(row => !row.ok);
    const written = ok.reduce((n, row) => n + row.written, 0);
    const okSum = ok.reduce((sum, row) => sum + big(row.amount_vnd), 0n).toString();
    const okText = ok.length ? `Đã ghi ${written} phiếu ở ${ok.length} sổ, tổng ${esc(F.short(okSum))}. Ghi nhầm thì mở sổ để hủy: `
      + `${ok.map(row => `<a href="${href(row.customer_id)}">${esc(label(row))}</a>`).join(', ')}.` : '';
    const badText = bad.length ? ` ${bad.length} sổ chưa ghi xong (lý do ở từng dòng).${result.unknown ? ' <button type="button" class="btn" data-write-retry>Thử lại</button>' : ''}` : '';
    return `<p class="inbox-result${bad.length ? ' warn' : ''}" role="status">${okText}${badText}</p>`;
  }

  // L2 của UX bước 03 (P3a): máy đã tự lấy chữ theo Sheet hôm nay, mỗi dòng có đường mở sổ để sửa lại tại ô.
  const AUTO_FIELD = { carrier: 'hãng tàu', shipper: 'shipper', origin: 'nơi đi', destination: 'nơi đến' };
  // P3b: chuyến mới máy đã đưa vào sổ hôm nay (chưa có giá); chuyến nghi trùng nằm ở "chờ kiểm" của sổ.
  function autoHtml(auto, esc, label, href) {
    const link = item => `<a href="${href(item.customer_id)}">${esc(label(item))}</a> · ${esc(item.container ?? '')}`;
    const text = auto?.today_count ? `<details class="auto-done"><summary>Máy đã tự lấy theo Sheet hôm nay: <b>${auto.today_count}</b> ô chữ ở <b>${auto.today_books}</b> sổ</summary>`
      + `<ul>${(auto.items ?? []).map(item => `<li>${link(item)} · ${esc(AUTO_FIELD[item.field] ?? item.field)}: ${esc(item.before ?? '—')} → <b>${esc(item.after)}</b></li>`).join('')}</ul>`
      + '<p class="tiny">Không đụng tiền. Sai ô nào thì mở sổ, sửa lại tại ô (có ghi Lịch sử).</p></details>' : '';
    const pending = auto?.today_trips_pending ? `, ${auto.today_trips_pending} chuyến vào chờ kiểm` : '';
    const trips = auto?.today_trips ? `<details class="auto-done"><summary>Máy đã đưa vào sổ hôm nay: <b>${auto.today_trips}</b> chuyến mới ở <b>${auto.today_trip_books}</b> sổ${pending}</summary>`
      + `<ul>${(auto.trip_items ?? []).map(item => `<li>${link(item)} · ${esc(dayText(item.event_date))}${item.pending ? ' · <span class="tag warn">chờ kiểm</span>' : ''}</li>`).join('')}</ul>`
      + '<p class="tiny">Chuyến chưa có giá, chưa cộng vào nợ. Sai chuyến nào thì mở sổ, xóa chuyến đó (có ghi Lịch sử).</p></details>' : '';
    return text + trips;
  }

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
  function render(data, { F, esc, label, href, failedText, selected, review, result, busy }) {
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
    const groups = GROUPS.map(group => ({ group, ...(group.key === 'receipts'
      ? receiptRows(books, F, esc, label, href, { selected, result, busy }) : rows(books, group, F, esc, label, href)) }))
      .filter(part => part.sorted.length);
    const textBooks = books.filter(b => b.text_diff > 0);
    const textCount = textBooks.reduce((sum, b) => sum + b.text_diff, 0);
    const autoDone = autoHtml(data.auto, esc, label, href);
    if (!groups.length && !textCount) return card(aside, `${resultHtml(result, F, esc, label, href)}${autoDone}${failed}<p class="empty">Không còn việc từ Sheet.</p>`);
    const total = groups.reduce((sum, part) => sum + part.sorted.reduce((n, b) => n + part.group.count(b), 0), 0);
    const money = books.reduce((sum, b) => sum + big(b.receipts.amount_vnd), 0n);
    const bookCount = new Set(groups.flatMap(part => part.sorted.map(b => b.customer_id))).size;
    const summary = total ? `<p class="inbox-summary">Còn <b>${total}</b> việc ở <b>${bookCount}</b> sổ${money ? ` · phiếu thu chờ ghi <b>${esc(F.short(money.toString()))}</b>` : ''}</p>` : '';
    const body = groups.map(({ group, sorted, html }) => {
      const n = sorted.reduce((sum, b) => sum + group.count(b), 0);
      const extra = group.key === 'receipts' && review?.length ? reviewHtml(review, F, esc, label, busy) : '';
      return `<div class="todo-group" data-group="${group.key}"><div class="todo-title"><span>${group.title}</span><span class="tag ${group.tone}">${n} ${group.unit}</span></div>${html}${extra}</div>`;
    }).join('');
    const text = textCount ? `<p class="inbox-note">Lệch chữ nơi đi, nơi đến, shipper: ${textCount} chỗ ở ${textBooks.length} sổ. Không đụng tiền; `
      + `${data.auto?.text_enabled ? 'máy lấy theo Sheet ở lượt tính tới (chỗ còn lại là dòng thiếu shipper trên Sheet hoặc Sheet để trống).' : 'máy chưa bật tự lấy theo Sheet.'}</p>` : '';
    return card(aside, `${summary}${resultHtml(result, F, esc, label, href)}${autoDone}${failed}${body}${text}`);
  }

  return { render, canWrite, reviewLine, GROUPS, REASONS };
}));
