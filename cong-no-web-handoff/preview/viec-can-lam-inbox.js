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
    return auto?.today_count || auto?.today_trips || auto?.today_prices ? `<ul aria-label="Việc máy làm hôm nay">${text}${trips}${prices}</ul>` : '';
  }

  const changePreview = (total, before, after) => (BigInt(total) - BigInt(before) + BigInt(after)).toString();
  return { canWrite, reviewLine, reviewHtml, resultHtml, autoHtml, changePreview, dayText };
}));
