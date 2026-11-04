/* Hộp ngoại lệ (specs/v7-hop-ngoai-le-p1.md, -p2.md): khối "Từ Sheet chờ đưa vào sổ" của tab Việc cần làm.
   Đọc GET /api/v7/inbox (API tính nền việc hàng chờ của mọi sổ). Mỗi dòng mở đúng sổ. Từ P2 nhóm phiếu thu ghi được
   ngay tại hộp: chọn sổ → xem lại nợ trước/sau → ghi bằng lệnh duyệt đang có của từng sổ (viec-can-lam.js gửi lệnh). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InboxCard = api;
}(typeof self !== 'undefined' ? self : this, function () {
  const big = value => BigInt(/^-?\d+$/.test(String(value ?? '')) ? value : 0);

  // Sổ ghi được phiếu tại hộp: có phiếu sẵn sàng và đủ phiên bản sổ, bản chụp để gửi lệnh duyệt.
  const canWrite = b => b.receipts?.ready > 0 && /^[0-9]+$/.test(String(b.receipts.ready_amount_vnd ?? '')) && big(b.receipts.ready_amount_vnd) > 0n && /^-?[0-9]+$/.test(String(b.outstanding_vnd ?? '')) && Number.isInteger(b.version) && /^[0-9a-f]{64}$/.test(b.receipts.snapshot_sha256 ?? '');
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

  function reviewHtml(books, F, esc, label, busy) {
    const lines = books.map(b => ({ b, line: reviewLine(b, F) }));
    const count = lines.reduce((n, { line }) => n + line.count, 0);
    const total = lines.reduce((sum, { line }) => sum + big(line.total), 0n);
    const million = value => globalThis.InboxTable.million(value);
    const rowsHtml = lines.map(({ b, line }) => `<tr><td>${esc(label(b))}</td><td>${line.count} phiếu thu (−${million(line.total)})</td>`
      + `<td class="num money" title="${line.before === null ? '' : esc(`${F.full(line.before)} → ${F.full(line.after)}`)}">${line.before === null ? '—' : `${million(line.before)} → <b>${million(line.after)}</b>`}</td>`
      + `<td>${line.notes.map(note => `<span class="tag warning">${esc(note)}</span>`).join(' ')}</td></tr>`).join('');
    return `<div class="receipt-review" role="dialog" aria-labelledby="h-review"><h3 id="h-review" title="Tổng ${esc(F.full(total.toString()))}">Xem lại trước khi ghi · ${count} phiếu thu ở ${books.length} sổ</h3>`
      + `<table><thead><tr><th>Khách</th><th>Ghi</th><th class="num" title="Tạm tính; số thật lấy lại sau khi ghi">Còn nợ trước → sau <span class="muted">tr</span></th><th>Lưu ý</th></tr></thead><tbody>${rowsHtml}</tbody></table>`
      + '<p>Phiếu ghi đúng ngày trên Sheet, trừ vào nợ cũ trước. Chuyến có giá thì bắt đầu cộng vào nợ.</p>'
      + `<div class="actions"><button type="button" class="btn primary" data-write${busy ? ' disabled' : ''}>${busy ? 'Đang ghi…' : `Ghi ${count} mục`}</button>`
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
  // MAY-GIA-01: giá Sheet máy đã ghi hôm nay (tiền vào sổ), tháng khóa thì máy đã mở rồi khóa lại.
  function autoHtml(auto, esc, label, href) {
    const million = value => globalThis.InboxTable.million(value);
    const text = (auto?.items ?? []).map(item => `<li><span class="auto-kind">Sửa chữ</span><strong>${esc(label(item))}</strong><span>${esc(AUTO_FIELD[item.field] ?? item.field)}: ${esc(item.before ?? '—')} → ${esc(item.after)}</span><a href="${href(item.customer_id)}">Mở sổ</a></li>`).join('');
    const trips = (auto?.trip_items ?? []).map(item => `<li><span class="auto-kind">${item.road ? 'Chuyến bộ' : 'Chuyến mới'}</span><strong>${esc(label(item))}</strong><span>${esc(item.container ?? '')} · ${esc(dayText(item.event_date))}${item.pending ? ' · chờ kiểm' : ''}</span><a href="${href(item.customer_id)}">Mở sổ</a></li>`).join('');
    // Trước → sau: chuyến chưa giá nhận giá Sheet; chuyến đã có giá chỉ đổi giảm trừ (phụ phí âm), đơn giá giữ nguyên.
    const fee = value => value != null && value !== '0';
    const priceChange = item => item.before_unit_price_vnd == null
      ? `chưa giá → ${million(item.unit_price_vnd)} tr${fee(item.other_fee_vnd) ? `, phụ phí ${million(item.other_fee_vnd)} tr` : ''}`
      : `${million(item.unit_price_vnd)} tr, phụ phí ${million(item.before_other_fee_vnd ?? '0')} → ${million(item.other_fee_vnd ?? '0')} tr`;
    const prices = (auto?.price_items ?? []).map(item => `<li><span class="auto-kind">Giá</span><strong>${esc(label(item))}</strong><span>${esc(item.container ?? '')} · ${esc(dayText(item.date))} · ${esc(priceChange(item))}${item.locked ? ' · tháng khóa' : ''}</span><a href="${href(item.customer_id)}">Mở sổ</a></li>`).join('');
    const fees = (auto?.ps_items ?? []).map(item => `<li><span class="auto-kind">Phụ phí</span><strong>${esc(label(item))}</strong><span>${esc(item.container ?? '')} · ${esc(dayText(item.date))} · phân loại theo PS, tổng không đổi${item.locked ? ' · tháng khóa' : ''}</span><a href="${href(item.customer_id)}">Mở sổ</a></li>`).join('');
    return auto?.today_count || auto?.today_trips || auto?.today_prices || auto?.today_ps ? `<ul aria-label="Việc máy làm hôm nay">${text}${trips}${prices}${fees}</ul>` : '';
  }

  // MAY-DOI-SOAT-01: kết quả lượt máy tự đối soát gần nhất, trả lời "web có đúng với Sheet không, máy vừa sửa gì, còn gì phải quyết".
  const GROUP_WORD = { receipts: 'phiếu thu', receipts_no_date: 'phiếu không ngày', receipts_edited: 'phiếu Sheet đã sửa', prices: 'giá', fee_rows: 'dòng tiền không container', fee_undo: 'dòng điều chỉnh Sheet không còn' };
  const REASON_TEXT = {
    WEB_AHEAD: 'Web đi trước Sheet: chuyến đã có giá trên web, Sheet chưa ghi. Không cần làm gì.',
    WOULD_FIX: 'Máy sửa được khi bật ghi, khớp đúng tới từng đồng.',
    NO_EXACT_FIX: 'Máy không tìm được cách khớp đúng tới từng đồng, nên chưa ghi gì.',
    SHEET_SHUFFLED: 'Trên Sheet đơn giá của vài chuyến đổi chỗ cho nhau, có thể do xếp lệch cột, nên máy không ghi.',
    AMBIGUOUS_FIX: 'Có nhiều cách khớp, máy không tự chọn.',
    NOTHING_TO_WRITE: 'Trên Sheet không có việc nào giải thích được số lệch.',
    TOO_MANY_GROUPS: 'Quá nhiều loại việc, máy không dò.',
    TOO_MANY_DIFFERENT: 'Quá nhiều khách lệch cùng lúc, máy chỉ báo, không ghi.',
    VERIFY_FAILED: 'Máy đã ghi nhưng tổng chưa khớp. Cần xem ngay.',
    WRITE_ERROR: 'Máy ghi chưa xong, lượt sau thử lại.',
    CHECK_ERROR: 'Máy chưa kiểm được khách này, lượt sau thử lại.',
    HELD: 'Sheet của khách này có chỗ máy chưa đọc được (số dư tự lệch hoặc thiếu số), chưa so được.',
    CHI_CO_SHEET: 'Có trên Sheet, chưa có sổ trên web.',
    CHI_CO_WEB: 'Có sổ trên web, không thấy trên Sheet.',
    THIEU_SO: 'Một bên chưa có tổng.',
  };
  const isAhead = row => row.reason === 'WEB_AHEAD' || (row.reason === 'FIXED' && row.status !== 'KHOP');
  const clock = iso => new Date(iso).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });
  const vnDay = ms => new Date(ms).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
  // Timer chạy mỗi giờ từ 7 tới 22 giờ: quá 3 giờ trong khung đó là máy đã dừng; đêm thì lần cuối là 22 giờ, không tính là cũ.
  function reconcileOld(checkedAt, now) {
    const hour = Number(new Date(now).toLocaleString('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', hour12: false }));
    return hour >= 10 && hour <= 22 && now - Date.parse(checkedAt) > 3 * 3600_000;
  }
  const shuffledText = row => (row.shuffled_months?.length ? ` Tháng có đơn giá đổi chỗ: ${row.shuffled_months.map(monthShort).join(', ')}.` : '');
  function reconcileRowText(row, million) {
    if (row.reason === 'FIXED') {
      const w = row.written ?? {};
      const parts = [w.receipts && `${w.receipts} phiếu thu`, w.legacy_deleted && `thay ${w.legacy_deleted} khoản thu cũ`, w.prices && `${w.prices} giá`, w.fee_rows && `${w.fee_rows} dòng điều chỉnh`, w.fee_undone && `hủy ${w.fee_undone} dòng điều chỉnh Sheet không còn`].filter(Boolean);
      return `Máy đã sửa ${parts.join(', ')}${row.fixed_at ? ` lúc ${clock(row.fixed_at)}` : ''}. ${row.status === 'KHOP' ? 'Khớp tới từng đồng.' : 'Phần còn lại là web đi trước Sheet.'}${shuffledText(row)}`;
    }
    const base = REASON_TEXT[row.reason] ?? row.reason;
    const shown = (row.groups ?? []).filter(g => row.reason !== 'WOULD_FIX' || g.chosen);
    const money = value => `${BigInt(value) > 0n ? '+' : ''}${million(value)} tr`;
    const work = shown.length ? ` ${row.reason === 'WOULD_FIX' ? 'Sẽ ghi' : 'Việc đang chờ'}: ${shown.map(g => `${g.count} ${GROUP_WORD[g.kind] ?? g.kind} (${money(g.delta_vnd)})`).join(', ')}.` : '';
    const ahead = row.reason !== 'WEB_AHEAD' && BigInt(row.web_ahead_vnd ?? 0) > 0n ? ` Trong số lệch có ${million(row.web_ahead_vnd)} tr web đi trước Sheet.` : '';
    return `${base}${work}${ahead}${shuffledText(row)}`;
  }
  function reconcileHtml(result, { esc, href, show, now = Date.now() }) {
    if (!result) return '';
    const million = value => globalThis.InboxTable.million(value);
    const when = iso => `${clock(iso)}${vnDay(Date.parse(iso)) === vnDay(now) ? '' : ` ngày ${dayText(vnDay(Date.parse(iso))).slice(0, 5)}`}`;
    const failed = result.last_error ? `<p class="reconcile-error" role="alert">Lần đối soát lúc ${esc(when(result.last_error.at))} chưa chạy được (${esc(result.last_error.reason)}).${result.checked_at ? ' Số dưới đây là của lần trước.' : ''}</p>` : '';
    if (!result.checked_at) return `<section class="reconcile warn" aria-label="Đối soát với Sheet">${failed}</section>`;
    const rows = result.customers ?? [];
    const fixed = rows.filter(row => row.reason === 'FIXED');
    const ahead = rows.filter(isAhead);
    const would = rows.filter(row => row.reason === 'WOULD_FIX');
    const open = rows.filter(row => row.reason !== 'FIXED' && row.reason !== 'WOULD_FIX' && !isAhead(row));
    const old = reconcileOld(result.checked_at, now);
    const tone = rows.some(row => row.reason === 'VERIFY_FAILED') ? 'danger' : open.length || would.length || failed || old ? 'warn' : '';
    const parts = [fixed.length && `hôm nay máy đã sửa ${fixed.length} khách`, would.length && `${would.length} khách máy sửa được`, ahead.length && `${ahead.length} khách web đi trước Sheet`].filter(Boolean);
    const big = value => { const n = BigInt(value ?? 0); return n < 0n ? -n : n; };
    // Nợ tập trung ở vài khách lớn: đếm khách một mình dễ tưởng gần xong, nên kèm tỷ lệ theo tiền.
    const share = BigInt(result.all_web_vnd ?? 0) > 0n ? ` (${BigInt(result.matched_web_vnd ?? 0) * 100n / BigInt(result.all_web_vnd)}% số nợ)` : '';
    const rank = row => (open.includes(row) ? 0 : would.includes(row) ? 1 : isAhead(row) && row.reason !== 'FIXED' ? 2 : 3);
    const sorted = [...rows].sort((a, b) => rank(a) - rank(b) || (big(b.difference_vnd) > big(a.difference_vnd) ? 1 : big(b.difference_vnd) < big(a.difference_vnd) ? -1 : 0));
    const line = row => `<tr><th scope="row">${esc(row.customer)}</th><td class="num money">${row.difference_vnd == null ? '—' : esc(million(row.difference_vnd))}</td><td>${esc(reconcileRowText(row, million))}</td><td>${row.customer_id ? `<a href="${href(row.customer_id)}">Mở sổ</a>` : ''}</td></tr>`;
    const months = result.months_differ?.length ? `<p class="inbox-note">${result.months_differ.length} khách khớp tổng nhưng chia theo tháng khác Sheet (web trừ nợ cũ trước).</p>` : '';
    const list = show && rows.length ? `<div class="reconcile-list"><table><thead><tr><th scope="col">Khách</th><th scope="col" class="num">Web − Sheet <span class="muted">tr</span></th><th scope="col">Kết luận</th><th scope="col"><span class="sr-only">Mở</span></th></tr></thead><tbody>${sorted.map(line).join('')}</tbody></table>${months}</div>` : '';
    return `<section class="reconcile ${tone}" aria-label="Đối soát với Sheet">${failed}<div class="reconcile-line"><span>Đối soát với Sheet lúc ${esc(when(result.checked_at))}${old ? ' · có thể cũ' : ''}</span><strong>${result.counts?.KHOP ?? 0}/${result.total ?? 0} khách khớp${share}</strong>${parts.map(text => `<span>${esc(text)}</span>`).join('')}${open.length ? `<strong class="reconcile-open">${open.length} khách cần xem</strong>` : ''}${rows.length ? `<button class="btn" type="button" data-reconcile aria-expanded="${!!show}">${show ? 'Thu gọn' : 'Xem'}</button>` : ''}</div>${list}</section>`;
  }

  const changePreview = (total, before, after) => (BigInt(total) - BigInt(before) + BigInt(after)).toString();
  return { canWrite, reviewLine, reviewHtml, resultHtml, autoHtml, reconcileHtml, changePreview, dayText };
}));
