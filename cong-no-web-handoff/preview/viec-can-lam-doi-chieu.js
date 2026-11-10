/* Việc cần làm (VIEC-DOI-CHIEU-01): dòng đầu trang, ba tab, bảng khách lệch, bảng đối chiếu, nhật ký máy. Chỉ vẽ; số do DoiChieuModel tính. */
globalThis.DoiChieuView = (() => {
  'use strict';
  const M = globalThis.DoiChieuModel;
  const REASON_TEXT = {
    WEB_AHEAD: 'Web đi trước Sheet: chuyến đã có giá trên web, Sheet chưa ghi. Không cần làm gì.',
    WOULD_FIX: 'Máy sửa được khi bật ghi, khớp đúng tới từng đồng.',
    BOOK_CREATED: 'Máy đã tạo sổ mới theo TONG và đưa đủ các dòng của tab vào. Khớp tới từng đồng.',
    WOULD_CREATE_BOOK: 'Máy tạo được sổ mới khi bật ghi.',
    BOOK_OVERLAP: 'Tab có container đã nằm ở sổ khác, có thể là đổi tên hoặc tách sổ, nên máy không tự tạo sổ.',
    TOO_MANY_NEW_BOOKS: 'Quá nhiều tab mới cùng lúc, máy chỉ báo, không tạo sổ.',
    NO_EXACT_FIX: 'Không có cách nào khớp đúng tới từng đồng, nên máy chưa ghi.',
    SHEET_SHUFFLED: 'Đơn giá của vài chuyến đổi chỗ trên Sheet, có thể do xếp lệch cột, nên máy không ghi.',
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
  const OUTSIDE_TEXT = { NOT_ON_TONG: 'Tab còn nợ, chưa có trên TONG, máy chưa tạo được sổ.', TONG_DIFFERS: 'Số trên TONG khác số trên tab, máy chưa tạo được sổ.', TAB_UNREADABLE: 'Tab có chỗ máy chưa đọc được, chưa tạo được sổ.' };
  const clock = iso => new Date(iso).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });
  const vnDay = ms => new Date(ms).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
  const dayShort = iso => (iso ? `${String(iso).slice(8, 10)}/${String(iso).slice(5, 7)}` : '—');
  const monthWord = month => { const number = Number(String(month).slice(5, 7)); return number ? `tháng ${number}` : ''; };
  const monthsShort = list => list.map(month => `T${Number(String(month).slice(5, 7))}`).join(', ');
  const when = (iso, now) => `${clock(iso)}${vnDay(Date.parse(iso)) === vnDay(now) ? '' : ` ngày ${dayShort(vnDay(Date.parse(iso)))}`}`;
  const million = value => globalThis.InboxTable.million(value);
  const icon = (name, size) => globalThis.InboxTable.icon(name, size);

  // Số lệch nhỏ không được làm tròn thành 0: 40.000 đồng vẫn là lệch.
  function money(value, F, signed = false) {
    if (value === null || value === undefined) return '—';
    const n = BigInt(value), size = n < 0n ? -n : n;
    const sign = n < 0n ? '−' : signed && n > 0n ? '+' : '';
    if (n !== 0n && size < 50000n) return `${sign}${F.full(size.toString())}`;
    return `${sign}${million(size.toString())}`;
  }

  // Tiền trong câu chữ: số nhỏ ghi đủ đồng, số lớn ghi triệu; không dấu vì câu đã nói chiều.
  function say(value, F) {
    const n = BigInt(value), size = n < 0n ? -n : n;
    return n !== 0n && size < 50000n ? F.full(size.toString()) : `${million(size.toString())} tr`;   // F.full đã có " đ"
  }

  // Câu ở cột "Vì sao": có gợi ý thì nói chỗ máy tìm ra, tối đa hai câu; đủ cả thì ở bảng đối chiếu khi mở.
  function hintLead(row, F) {
    const texts = M.hintTexts(row, value => say(value, F));
    if (!texts.length) return null;
    const head = row.reason === 'HELD' ? 'Sheet có chỗ máy chưa đọc được, chưa so được. ' : row.hints_explain ? 'Có tổ hợp gợi ý khớp số tiền lệch, cần kiểm chứng: ' : 'Máy chưa chắc, có thể do: ';
    const more = texts.length > 2 ? ` Còn ${texts.length - 2} chỗ nữa, mở để xem.` : '';
    return `${head}${texts.slice(0, 2).join(' ')}${more}`;
  }

  function whyText(row, now, F) {
    if (row.hints_stale) return 'Gợi ý của lượt đối soát chưa được xác nhận với sổ và nguồn hiện tại. Mở đối chiếu; nếu dữ liệu đã đổi, chờ lượt đối soát mới.';
    const shuffled = row.shuffled_months?.length ? ` Tháng có đơn giá đổi chỗ: ${monthsShort(row.shuffled_months)}.` : '';
    const editing = row.sheet_editing ? `Sheet vừa sửa lúc ${when(row.sheet_last_edit_at, now)}, máy xem lại ở lượt sau. ` : '';
    const lastEdit = !row.sheet_editing && row.sheet_last_edit_at && !/^WOULD_/.test(row.reason) ? ` Sheet sửa lần cuối lúc ${when(row.sheet_last_edit_at, now)}.` : '';
    const lead = hintLead(row, F);
    return `${editing}${lead ?? REASON_TEXT[row.reason] ?? row.reason}${shuffled}${lastEdit}`;
  }

  // Dòng đầu trang: câu trả lời cho "số nợ có đúng không".
  function statusHtml(reconcile, { esc, now, stale, computing, nothing }) {
    const refreshing = stale ? '<span class="muted refreshing" role="status">Đang cập nhật…</span>' : '';
    const working = computing ? `<span class="computing">${esc(computing)}</span>` : '';
    const failed = reconcile?.last_error ? `<p class="status-error" role="alert">Lần đối soát lúc ${esc(when(reconcile.last_error.at, now))} chưa chạy được (${esc(reconcile.last_error.reason)}).${reconcile.checked_at ? ' Số dưới đây là của lần trước.' : ''}</p>` : '';
    if (!reconcile?.checked_at) return `<section class="viec-status warn" aria-label="Đối soát với Sheet"><div class="status-line"><i aria-hidden="true"></i><strong>${esc(nothing ?? 'Chưa có lượt đối soát')}</strong>${working}${refreshing}</div>${failed}</section>`;
    const rows = M.openRows(reconcile);
    const outside = reconcile.outside_tabs ?? [];
    const old = M.isOld(reconcile.checked_at, now);
    const verify = rows.some(row => row.reason === 'VERIFY_FAILED');
    const tone = verify ? 'danger' : rows.length || outside.length || failed || old ? 'warn' : '';
    const share = M.share(reconcile);
    const facts = [share !== null && `${share}% số nợ`, rows.length && `${rows.length} khách lệch`, outside.length && `${outside.length} tab chưa có sổ`, old && 'có thể cũ'].filter(Boolean).join(' · ');
    return `<section class="viec-status ${tone}" aria-label="Đối soát với Sheet"><div class="status-line"><i aria-hidden="true"></i><strong>${reconcile.counts?.KHOP ?? 0}/${reconcile.total ?? 0} khách khớp Sheet</strong><span>${esc(facts)}</span>${working}${refreshing}<span class="status-time">Đối soát lúc ${esc(when(reconcile.checked_at, now))} · lần tới ${esc(M.nextCheck(now))}</span></div>${failed}</section>`;
  }

  function tabsHtml(current, counts) {
    const tabs = [['lech', 'Số nợ lệch', counts.lech], ['don', 'Dọn chi tiết', counts.don], ['may', 'Đã làm', counts.may]];
    return `<div class="viec-tabs" role="tablist" aria-label="Khu việc">${tabs.map(([key, text, n]) => `<button type="button" role="tab" data-tab="${key}" aria-selected="${current === key}">${text} <span>${n}</span></button>`).join('')}</div>`;
  }

  const GROUP_NOTE = { receipts: 'có ngày trên Sheet', receipts_no_date: 'ngày lấy cuối tháng', fee_rows: 'ghi thành dòng điều chỉnh', fee_undo: 'Sheet không còn dòng này' };
  function groupTitle(group) {
    const month = group.month ? ` ${monthWord(group.month)}` : '';
    if (group.kind === 'prices') return `${M.isFeeOnly(group) ? 'Phụ phí' : 'Giá'} ${group.count} chuyến${month}`;
    if (group.kind === 'receipts') return `${group.count} phiếu thu`;
    if (group.kind === 'receipts_no_date') return `${group.count} phiếu thu không ngày${month}`;
    if (group.kind === 'receipts_edited') return `Thay ${group.replaces} khoản thu cũ bằng ${group.count} phiếu Sheet${month}`;
    if (group.kind === 'fee_rows') return `${group.count} dòng tiền không container${month}`;
    if (group.kind === 'fee_undo') return `Hủy ${group.count} dòng điều chỉnh của máy${month}`;
    return group.kind;
  }
  function groupNote(group, delta) {
    if (group.kind === 'prices') return BigInt(delta) > 0n ? 'Sheet cao hơn web' : 'Sheet thấp hơn web';
    if (group.kind === 'receipts_edited') return 'Sheet đã sửa phiếu';
    return GROUP_NOTE[group.kind] ?? '';
  }

  function rowsTable(group, off, { F, esc, locked }) {
    if (group.kind === 'prices') {
      const cell = value => (value === null || value === undefined ? 'trống' : million(value));
      return `<div class="dc-rows"><table><thead><tr><th scope="col"><span class="sr-only">Chọn</span></th><th scope="col">Container</th><th scope="col">Ngày</th><th scope="col" class="num">Đơn giá web → Sheet</th><th scope="col" class="num">Phụ phí web → Sheet</th><th scope="col" class="num">Nợ đổi</th><th scope="col" class="num">Dòng Sheet</th><th scope="col"><span class="sr-only">Giữ</span></th></tr></thead><tbody>${group.rows.map(row => {
        const same = row.web_unit_price_vnd === row.sheet_unit_price_vnd;
        return `<tr><td><input type="checkbox" data-dc-row="${esc(row.key)}" data-group="${esc(group.id)}" aria-label="Chọn ${esc(row.container ?? row.key)}"${off.has(row.key) ? '' : ' checked'}${locked ? ' disabled' : ''}></td><th scope="row">${esc(row.container ?? '—')}</th><td>${esc(dayShort(row.date))}</td><td class="num">${same ? cell(row.sheet_unit_price_vnd) : `${cell(row.web_unit_price_vnd)} → <strong>${cell(row.sheet_unit_price_vnd)}</strong>`}</td><td class="num" title="${esc(`${row.web_other_fee_vnd === null ? 'trống' : F.full(row.web_other_fee_vnd)} → ${row.sheet_other_fee_vnd === null ? 'trống' : F.full(row.sheet_other_fee_vnd)}`)}">${cell(row.web_other_fee_vnd)} → <strong>${cell(row.sheet_other_fee_vnd)}</strong></td><td class="num" title="${esc(F.full(row.delta_vnd))}"><b>${money(row.delta_vnd, F, true)}</b></td><td class="num">${row.source_row ?? '—'}</td><td class="num">${row.status === 'CONFLICT' && row.source_fingerprint ? `<button type="button" class="dc-link" data-dc-giu-row="${esc(row.key)}"${locked ? ' disabled' : ''}>Giữ số web</button>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`;
    }
    return `<div class="dc-rows"><table><thead><tr><th scope="col">Dòng Sheet</th><th scope="col">Ghi chú</th><th scope="col" class="num">Số tiền</th></tr></thead><tbody>${group.rows.map(row => `<tr><th scope="row">${row.source_row ?? row.id ?? '—'}</th><td>${esc(row.note ?? '')}</td><td class="num" title="${row.amount_vnd ? esc(F.full(row.amount_vnd)) : ''}">${money(row.amount_vnd, F)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  // Bảng đối chiếu của một khách: số web ± từng khoản = số Sheet, phần chưa giải thích hiện riêng.
  function statementHtml(id, statement, state, { F, esc, href, now, action, busy, hints = [] }) {
    const link = `<a class="dc-open-book" href="${href(id)}">Mở cả sổ ${icon('right')}</a>`;
    if (statement === undefined) return '<p class="loading dc-loading">Đang tính các khoản…</p>';
    if (statement === null) return `<p class="dc-failed" role="alert">Không đọc được các khoản từ Sheet. <button type="button" class="btn" data-dc-retry="${id}">Thử lại</button> ${link}</p>`;
    const selected = state.sel.get(id) ?? new Set();
    const off = state.off.get(id) ?? new Set();
    const kept = state.kept.get(id) ?? new Set();
    const sum = M.summarize(statement, selected, off);
    const pending = action?.rowKey === `dc:${id}`;
    const locked = pending || busy;
    const groups = statement.groups.map(group => {
      const delta = M.groupDelta(group, off).toString();
      const on = selected.has(group.id);
      const open = state.xem.has(group.id);
      const canKeep = group.kind === 'prices' && group.rows.some(row => row.status === 'CONFLICT' && row.source_fingerprint);
      const partial = group.kind === 'prices' && off.size && group.rows.some(row => off.has(row.key));
      const note = partial ? `đã chọn ${group.rows.filter(row => !off.has(row.key)).length}/${group.count} chuyến` : groupNote(group, group.delta_vnd);
      return `<div class="dc-row dc-item${on ? ' on' : ''}" data-dc-group="${esc(group.id)}"><label class="dc-pick"><input type="checkbox" data-dc-pick="${esc(group.id)}"${on ? ' checked' : ''}${locked ? ' disabled' : ''} aria-label="Ghi khoản ${esc(groupTitle(group))}"><span><strong>${esc(groupTitle(group))}</strong>${note ? ` <span class="dc-note">· ${esc(note)}</span>` : ''}${group.locked ? ' <span class="dc-note">· tháng khóa</span>' : ''}</span></label><button type="button" class="dc-link" data-dc-xem="${esc(group.id)}" aria-expanded="${open}">${open ? 'Thu gọn' : group.kind === 'prices' ? 'Xem từng chuyến' : 'Xem chi tiết'}</button>${canKeep ? `<button type="button" class="dc-link quiet" data-dc-giu="${esc(group.id)}"${locked ? ' disabled' : ''}>Giữ số web</button>` : ''}<span class="dc-num" title="${esc(F.full(delta))}">${money(delta, F, true)}</span></div>${open ? rowsTable(group, off, { F, esc, locked }) : ''}`;
    }).join('');
    const ahead = BigInt(statement.web_ahead_vnd ?? 0) > 0n ? `<div class="dc-row"><span class="dc-label">Web đi trước Sheet <span class="dc-note">· chuyến Sheet chưa ghi giá, không phải lệch</span></span><span class="dc-num" title="${esc(F.full(statement.web_ahead_vnd))}">${money(statement.web_ahead_vnd, F)}</span></div>` : '';
    const remaining = sum.remaining === null ? null : BigInt(sum.remaining);
    const left = remaining === null
      ? `<div class="dc-row dc-left unknown"><strong>Chưa so được</strong><span class="dc-hint">Lượt đối soát chưa có tổng Sheet của khách này.</span><strong class="dc-num">—</strong></div>`
      : remaining === 0n
        ? `<div class="dc-row dc-left ok"><strong>Khớp</strong><span class="dc-hint">Khớp tới từng đồng${sum.items.length ? ' sau khi ghi' : ''}.</span><strong class="dc-num">0</strong></div>`
        : `<div class="dc-row dc-left"><strong>Còn lệch</strong><span class="dc-hint">${sum.items.length ? 'Sau khi ghi vẫn lệch. Xem lại tab khách trên Sheet.' : statement.groups.length ? 'Chọn khoản để xem còn lệch bao nhiêu.' : hints.length ? 'Máy chưa ghi được khoản nào. Các chỗ máy tìm ra ở dưới.' : 'Không có khoản nào giải thích được. Xem tab khách trên Sheet.'}</span><strong class="dc-num" title="${esc(F.full(sum.remaining))}">${money(sum.remaining, F, true)}</strong></div>`;
    const confirm = pending ? `<div class="dc-confirm" role="group" aria-labelledby="h-action"><p id="h-action" class="action-description">${esc(action.text)}</p>${action.error ? `<p role="alert" class="row-error">${esc(action.error)}</p>` : ''}${action.path ? `<button type="button" class="btn primary" data-action-write${busy ? ' disabled' : ''}>${busy ? 'Đang ghi…' : action.unknown ? 'Thử lại' : 'Xác nhận'}</button>` : ''}${action.unknown ? '' : `<button type="button" class="btn" data-action-cancel${busy ? ' disabled' : ''}>Thôi</button>`}</div>` : '';
    const undo = state.undo.get(id);
    const done = undo ? `<p class="dc-done" role="status">${esc(undo.text)}${undo.keys ? ` <button type="button" class="btn" data-dc-undo="${id}"${locked ? ' disabled' : ''}>Hoàn tác</button>` : undo.note ? ` ${esc(undo.note)}` : ''}</p>` : '';
    const buttons = pending ? '' : `<div class="dc-actions">${statement.groups.length ? `<button type="button" class="btn primary" data-dc-ghi="${id}"${sum.items.length && !locked ? '' : ' disabled'}>${sum.items.length ? `Ghi ${sum.items.length} khoản đã chọn` : 'Chọn khoản để ghi'}</button>` : ''}${statement.sheet_editing ? `<span class="dc-note">Không chọn gì thì máy xem lại lúc ${esc(M.nextCheck(now))}.</span>` : ''}${kept.size ? `<span class="dc-note">Đã giữ số web ${kept.size} dòng.</span>` : ''}${link}</div>`;
    const found = hints.length ? `<div class="dc-hints"><p><strong>Chỗ máy tìm ra</strong> <span class="dc-note">· máy không tự sửa, người sửa trên Sổ hoặc Sheet</span></p><ul>${hints.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : '';
    return `<div class="dc-sheet">${done}<div class="dc-table"><div class="dc-row"><span class="dc-label">Số nợ trên web</span><span class="dc-num" title="${esc(F.full(sum.web))}">${money(sum.web, F)}</span></div>${groups}${sum.items.length ? `<div class="dc-row dc-sub"><span class="dc-label">Số nợ web sau khi ghi</span><span class="dc-num" title="${esc(F.full(sum.after))}">${money(sum.after, F)}</span></div>` : ''}${ahead}<div class="dc-row dc-sheet-total"><span class="dc-label">Số nợ trên Sheet${statement.checked_at ? ` <span class="dc-note">· lúc ${esc(when(statement.checked_at, now))}</span>` : ''}</span><span class="dc-num"${sum.sheet ? ` title="${esc(F.full(sum.sheet))}"` : ''}>${money(sum.sheet, F)}</span></div>${left}</div>${found}${confirm}${buttons}</div>`;
  }

  function lechHtml(reconcile, state, { F, esc, href, now, action, busy, nothing, bookVersions }) {
    if (!reconcile?.checked_at) return `<p class="dc-empty">${esc(nothing ?? 'Chưa có kết quả đối soát nên chưa biết số nợ có đúng không.')}</p>`;
    const rows = M.openRows(reconcile);
    const outside = reconcile.outside_tabs ?? [];
    const ahead = M.aheadRows(reconcile);
    const row = original => {
      const item = M.currentHints(original, state.open === original.customer_id ? state.data.get(original.customer_id) : undefined,
        bookVersions?.get(original.customer_id), state.hintsUnverified?.has(original.customer_id));
      const id = item.customer_id;
      const open = id && state.open === id;
      const statement = open ? state.data.get(id) : undefined;
      const live = open && statement?.sheet_total_vnd != null ? M.summarize(statement).now : item.difference_vnd;
      const web = open && statement ? statement.web_vnd : item.web_total_vnd;
      return `<tr class="dc-customer${open ? ' expanded' : ''}" data-customer="${id ?? ''}"><th scope="row">${id ? `<button type="button" class="book-name" data-dc-open="${id}" aria-expanded="${open}" title="Mở đối chiếu ${esc(item.customer)}">${esc(item.customer)}</button>` : esc(item.customer)}</th><td class="num">${money(web, F)}</td><td class="num">${money(open && statement ? statement.sheet_total_vnd : item.sheet_total_vnd, F)}</td><td class="num dc-gap" title="${live === null || live === undefined ? '' : esc(F.full(live))}">${money(live, F, true)}</td><td class="dc-why">${esc(whyText(item, now, F))}</td><td class="dc-toggle">${id ? `<button type="button" class="row-toggle" data-dc-open="${id}" aria-expanded="${open}" aria-label="${open ? 'Đóng' : 'Mở'} đối chiếu ${esc(item.customer)}">${icon(open ? 'up' : 'down', 16)}</button>` : ''}</td></tr>${open ? `<tr class="dc-detail"><td colspan="6">${statementHtml(id, statement, state, { F, esc, href, now, action, busy, hints: M.hintTexts(item, value => say(value, F)) })}</td></tr>` : ''}`;
    };
    const outsideRows = outside.map(tab => `<tr class="dc-customer"><th scope="row">${esc(tab.customer)}</th><td class="num">—</td><td class="num">${money(tab.sheet_total_vnd, F)}</td><td class="num dc-gap">—</td><td class="dc-why">${esc(OUTSIDE_TEXT[tab.reason] ?? 'Tab còn nợ, máy chưa tạo được sổ.')}</td><td></td></tr>`).join('');
    const empty = !rows.length && !outside.length ? `<div class="dc-empty ok"><p><strong>Không có khách nào lệch. Chưa cần làm gì.</strong></p><p>Máy kiểm lại lúc ${esc(M.nextCheck(now))}. Email chỉ gửi khi máy lỗi hoặc dừng; khách lệch hiện ở đây.</p></div>` : '';
    const table = rows.length || outside.length ? `<div class="work-scroll dc-scroll"><table class="dc-customers"><thead><tr><th scope="col">Khách</th><th scope="col" class="num">Web <span class="muted">tr</span></th><th scope="col" class="num">Sheet <span class="muted">tr</span></th><th scope="col" class="num">Lệch <span class="muted">tr</span></th><th scope="col">Vì sao máy chưa tự sửa</th><th scope="col"><span class="sr-only">Mở</span></th></tr></thead><tbody>${rows.map(row).join('')}${outsideRows}</tbody></table></div>` : '';
    const aheadNote = ahead.length ? `<details class="dc-side"><summary>${ahead.length} khách web đi trước Sheet, không cần làm gì</summary><ul>${ahead.map(item => `<li><strong>${esc(item.customer)}</strong> ${money(item.difference_vnd, F, true)} tr${item.customer_id ? ` · <a href="${href(item.customer_id)}">Mở sổ</a>` : ''}</li>`).join('')}</ul></details>` : '';
    const months = reconcile.months_differ?.length ? `<p class="inbox-note">${reconcile.months_differ.length} khách khớp tổng nhưng chia theo tháng khác Sheet (web trừ nợ cũ trước).</p>` : '';
    return `${empty}${table}${aheadNote}${months}`;
  }

  const machineCount = (auto, reconcile) => (auto?.today_count ?? 0) + (auto?.today_trips ?? 0) + (auto?.today_prices ?? 0) + (auto?.today_ps ?? 0) + M.fixedRows(reconcile).length;

  // Tab Đã làm (HOAT-DONG-01): việc đã ghi của một ngày, mọi sổ, cả máy lẫn người, đọc từ Lịch sử trong DB (GET /api/v7/activity).
  // Câu chữ dùng chung với khung Lịch sử của sổ (so-khach-v7-lich-su-cau.js). Hôm nay thêm dòng "Đã ghi hôm nay" như trước.
  const MACHINE_ACTORS = new Set(['may-theo-sheet']);
  const isMachine = event => MACHINE_ACTORS.has(event.actor);
  const dayText = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const VND = value => (value === null || value === undefined ? '–' : BigInt(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'));
  const isoDay = value => (/^\d{4}-\d\d-\d\d$/.test(value ?? '') ? `${value.slice(8)}/${value.slice(5, 7)}/${value.slice(0, 4)}` : (value ?? ''));
  function sentences(body) {
    const feeTypes = body.fee_types ?? [];
    const lookup = { trips: body.trips ?? [], receipts: body.receipts ?? [], legacy_rows: body.legacy_rows ?? [] };
    return globalThis.LichSuCau.create({ fmt: VND, dateText: isoDay, monthKey: value => (typeof value === 'string' ? value.slice(0, 7) : ''),
      monthLabel: CongNoFormat.monthLabel, model: SoKhachV7Model,
      feeTypeName: id => feeTypes.find(type => Number(type.id) === Number(id))?.name ?? `Loại #${id}`, snapshot: () => lookup });
  }
  // Cột Ghi chú đã có tiêu đề nên bỏ chữ "Ghi chú:" đầu câu; lô nhiều chuyến cùng ghi chú thì chỉ hiện một lần.
  const noteCell = note => [...new Set(String(note ?? '').replace(/^Ghi chú:\s*/, '').split('; ').filter(Boolean))].join('; ');
  function activityItems(body, filter) {
    const cau = sentences(body);
    return (body.events ?? []).filter(event => filter === 'may' ? isMachine(event) : filter === 'nguoi' ? !isMachine(event) : true)
      .map(event => ({ event, label: cau.labelOf(event), text: cau.describeEvent(event), note: noteCell(cau.noteOf(event)),
        who: isMachine(event) ? 'Máy' : cau.actorName(event), group: cau.groupOf(event) }));
  }
  // Nhóm theo loại việc, cùng nhóm với bộ lọc Lịch sử của sổ; trong nhóm, cùng việc đứng liền nhau (việc có lần mới nhất lên trước),
  // mỗi việc mới nhất trước.
  const ACT_GROUPS = [['chuyen', 'Chuyến'], ['thu', 'Thu tiền'], ['gia', 'Giá và phụ phí'], ['khoa', 'Khóa tháng'], ['', 'Việc khác']];
  function activityGroups(items) {
    return ACT_GROUPS.map(([key, title]) => {
      const rows = items.filter(item => item.group === key);
      const labels = [...new Set(rows.map(item => item.label))];
      return { key, title, labels: labels.map(label => [label, rows.filter(item => item.label === label).length]),
        rows: labels.flatMap(label => rows.filter(item => item.label === label)) };
    }).filter(group => group.rows.length);
  }
  function mayHtml(act, people, { esc, href }) {
    const { day, today, filter, body } = act;
    const isToday = day === today;
    const prev = body?.prev_day, next = isToday ? null : body?.next_day && body.next_day <= today ? body.next_day : today;
    const events = body?.events ?? [];
    const machine = events.filter(isMachine).length;
    const chip = (key, text, n) => `<button type="button" class="filter-chip" data-act-filter="${key}" aria-pressed="${filter === key}">${text} <b>${n}</b></button>`;
    const chips = body ? `<div class="act-filter" role="group" aria-label="Lọc theo người làm">${chip('all', 'Tất cả', events.length)}${chip('may', 'Máy', machine)}${chip('nguoi', 'Người', events.length - machine)}</div>` : '';
    const bar = `<div class="act-bar"><button type="button" class="btn" data-act-day="${prev ?? ''}"${prev ? '' : ' disabled'} title="${prev ? `Ngày gần nhất có việc: ${esc(dayText(prev))}` : 'Không có ngày trước có việc'}">${icon('left', 16)}${prev ? esc(dayText(prev).slice(0, 5)) : 'Trước'}</button>`
      + `<label class="act-date">Ngày <input type="date" data-act-date value="${esc(day)}" max="${esc(today)}"></label>`
      + `<button type="button" class="btn" data-act-day="${next ?? ''}"${next ? '' : ' disabled'}>${next && next !== today ? esc(dayText(next).slice(0, 5)) : 'Sau'}${icon('right', 16)}</button>`
      + `${isToday ? '' : '<button type="button" class="btn" data-act-day="today">Hôm nay</button>'}${chips}</div>`;
    const head = isToday ? `<div class="today-inline"><span>Đã ghi hôm nay</span>${people || '<span class="muted">Chưa có giao dịch nào hôm nay.</span>'}</div>` : '';
    let list;
    if (body === undefined) list = '<p class="loading dc-loading">Đang tải việc đã ghi…</p>';
    else if (body === null) list = `<p class="dc-failed" role="alert">Không tải được việc đã ghi ngày ${esc(dayText(day))}. <button type="button" class="btn" data-act-retry>Thử lại</button></p>`;
    else {
      const items = activityItems(body, filter);
      const more = body.total > events.length ? `<p class="inbox-note">Ngày này có ${body.total} việc, đang hiện ${events.length} việc mới nhất.</p>` : '';
      const row = ({ event, label, text, note, who }) => `<tr><td class="act-time"><time>${esc(clock(event.at))}</time></td><td><span class="auto-kind${isMachine(event) ? ' machine' : ''}">${esc(who)}</span></td>`
        + `<th scope="row" class="act-book" title="${esc(event.customer ?? '')}">${esc(event.customer ?? `Sổ #${event.customer_id}`)}</th><td class="act-label">${esc(label)}</td>`
        + `<td class="act-what">${text ? esc(text) : '<span class="muted">—</span>'}</td><td class="act-note">${note ? esc(note) : ''}</td>`
        + `<td class="act-open">${event.customer_id ? `<a href="${href(event.customer_id)}">Mở sổ</a>` : ''}</td></tr>`;
      const group = ({ key, title, labels, rows }) => `<tbody class="act-group" data-act-group="${key || 'khac'}"><tr class="act-group-head"><th scope="rowgroup" colspan="7">`
        + `<span class="act-group-title">${esc(title)} <b>${rows.length}</b></span>${labels.length > 1 ? `<span class="act-group-kinds">${labels.map(([label, n]) => `${esc(label)} ${n}`).join(' · ')}</span>` : ''}</th></tr>${rows.map(row).join('')}</tbody>`;
      list = items.length ? `<div class="work-scroll act-scroll"><table class="act-table" aria-label="Việc đã ghi ngày ${esc(dayText(day))}"><thead><tr><th scope="col">Giờ</th><th scope="col">Người làm</th><th scope="col">Sổ</th><th scope="col">Việc</th><th scope="col">Chi tiết</th><th scope="col">Ghi chú</th><th scope="col"><span class="sr-only">Mở sổ</span></th></tr></thead>${activityGroups(items).map(group).join('')}</table></div>${more}`
        : `<p class="dc-empty">${events.length ? 'Không có việc nào của nhóm này.' : isToday ? 'Hôm nay chưa ai ghi gì.' : `Ngày ${esc(dayText(day))} không ai ghi gì.`}</p>`;
    }
    return `<section class="may-panel" aria-label="Việc đã ghi"><p class="dc-lead">Mọi lần ghi vào sổ, của máy và của người, theo ngày. Máy chỉ ghi tiền khi tổng khách khớp Sheet tới từng đồng. Thấy sai thì mở sổ sửa lại.</p>${bar}${head}${list}</section>`;
  }

  return { statusHtml, tabsHtml, lechHtml, mayHtml, machineCount, money };
})();
