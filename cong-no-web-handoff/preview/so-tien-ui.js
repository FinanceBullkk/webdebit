/* SO-TIEN P0-a lát 2: trang Sổ tiền (specs/so-tien-p0a-lat2.md, mục Màn hình) — mục tiêu: đưa sao kê vào sổ đúng một lần và thấy
 * số dư. Thứ tự đọc: thẻ số dư (tới ngày nào, thiếu ngày nào, lô chờ) → nhập file và xem trước (chỉ hiện chỗ cần quyết, bảng đủ
 * dòng mở khi bấm) → các lần nhập → giao dịch. Nút chỉ vẽ cho vai dùng được (vai thật vẫn kiểm trong hàm SQL). Không tính tiền ở
 * đây (ARCH-03): số đã tính ở SQL hoặc so-tien-model.js. Ghi qua DoiXeChung.tao: mã yêu cầu chống ghi trùng, một lệnh một lúc,
 * câu báo sau khi đọc lại. Ngày hôm nay lấy từ máy chủ (thẻ tài khoản, giờ VN). */
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = SoTienModel;
  const esc = F.esc;
  const API = '/api/v7/tien';
  const MAX_FILE = 4 * 1024 * 1024;
  const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
  const $ = selector => document.querySelector(selector);
  const params = new URLSearchParams(location.search);
  const S = {
    me: null, off: false, accounts: [], accountId: Number(params.get('account')) || null, card: null, imports: [],
    reviewId: Number(params.get('lo')) || null, review: null, choice: { lines: {}, keep: {} }, known: {}, showAll: false,
    month: MONTH.test(params.get('thang') ?? '') ? params.get('thang') : null, status: '', tx: null, txDesc: false,
    openTx: null, detail: null, template: null, busy: false, toast: null, giuBao: null,
  };
  const net = DoiXeChung.tao({
    S, draw, load, toastBox: $('#st-toast'), esc, tienTo: 'st', toastMs: 7000,
    matMang: 'Mất kết nối. Việc đang làm vẫn còn trên màn; bấm lại khi có mạng (không ghi hai lần).',
    taiLai: ['IMPORT_PREVIEW_STALE', 'STALE_VERSION', 'DAY_SIGNED', 'IMPORT_SUSPECT_UNRESOLVED'],
  });
  const can = role => M.has(S.card?.roles, role);
  const empty = text => `<section class="nd-card"><p class="st-empty">${esc(text)}</p></section>`;
  const dirText = d => (d === 'in' ? 'Thu' : d === 'out' ? 'Chi' : '—');

  function showError(text) {
    const box = $('#error');
    box.textContent = text;
    box.hidden = false;
  }

  async function loadReview() {
    S.review = await net.getJson(`${API}/imports/${S.reviewId}`);
    if (S.review.import.status !== 'validated') return;
    const { suspects, unmatched } = M.questions(S.review);
    const ids = new Set([...suspects.flatMap(s => s.candidates), ...unmatched.map(u => u.transaction_id)]);
    await Promise.all([...ids].filter(id => !S.known[id]).map(async id => {
      S.known[id] = (await net.getJson(`${API}/transactions/${id}`)).transaction;
    }));
  }

  async function load() {
    try {
      if (!S.me) {
        try {
          S.me = await net.getJson(`${API}/me`);
        } catch (e) {
          if (e.code !== 'TIEN_OFF') throw e;
          S.off = true;
        }
      }
      if (S.me?.visible) {
        S.accounts = (await net.getJson(`${API}/accounts`)).accounts;
        if (!S.accounts.some(a => a.id === S.accountId)) S.accountId = S.accounts[0]?.id ?? null;
      }
      if (S.me?.visible && S.accountId) {
        const id = S.accountId;
        const [card, imports] = await Promise.all([net.getJson(`${API}/accounts/${id}`), net.getJson(`${API}/accounts/${id}/imports`)]);
        S.card = card;
        S.imports = imports.imports;
        S.month ??= card.today.slice(0, 7);
        const [from, to] = M.monthRange(S.month, card.today);
        const tx = await net.getJson(`${API}/accounts/${id}/transactions?from=${from}&to=${to}`);
        S.tx = tx.transactions;
        S.txDesc = tx.description_visible;
        if (S.reviewId) await loadReview();
        if (S.openTx) S.detail = await net.getJson(`${API}/transactions/${S.openTx}`);
      }
      $('#error').hidden = true;
    } catch (e) {
      showError(e.message);
    }
    document.body.dataset.loaded = '1';
    draw();
  }

  // ---------- vẽ ----------
  function accountHtml() {
    const label = a => `${a.bank_code} ••••${a.account_last4} · ${a.currency}`;
    if (S.accounts.length > 1) {
      return `<label class="st-account"><span class="st-muted" hidden>Tài khoản</span><select data-act="account" data-f="account" aria-label="Tài khoản">${
        S.accounts.map(a => `<option value="${a.id}"${a.id === S.accountId ? ' selected' : ''}>${esc(label(a))}</option>`).join('')}</select></label>`;
    }
    const one = S.accounts.find(a => a.id === S.accountId);
    return one ? `<span class="st-account">${esc(label(one))}</span>` : '';
  }

  function cardHtml() {
    const c = S.card;
    const cov = c.coverage;
    if (c.opening === null) {
      return `<section class="nd-card" aria-label="Số dư"><div class="st-hero"><div><div class="st-label">Số dư theo sao kê</div><div class="st-amount">—</div>
        <div class="st-muted st-small">Tài khoản chưa có số dư mở. Người quản trị sổ tiền nhập số dư mở trước khi nhập sao kê.</div></div></div></section>`;
    }
    const until = !cov.data_until ? 'Chưa nhập sao kê nào.'
      : cov.data_until_state === 'full' ? `Dữ liệu tới hết ngày ${M.vnDate(cov.data_until)}.`
        : `Dữ liệu tới ngày ${M.vnDate(cov.data_until)}; ngày này chưa trọn (giao dịch sau giờ tải file có ở lần nhập sau).`;
    const facts = [];
    if (cov.data_until) {
      facts.push(cov.missing_count > 0
        ? `<li><span class="st-tag bad">Thiếu sao kê ${cov.missing_count} ngày</span><span class="st-small">${cov.missing_days.slice(0, 6).map(M.shortDate).join(', ')}${cov.missing_count > 6 ? '…' : ''}</span></li>`
        : '<li><span class="st-tag ok">Không có ngày trống giữa các lần nhập</span></li>');
      // Thường ngày cuối có dữ liệu là hôm nay (tải lúc 17h) hoặc hôm qua (trước 17h); cũ hơn thì nhắc, không gọi là "đủ".
      const gap = M.daysBetween(cov.data_until, c.today);
      if (gap >= 2) facts.push(`<li><span class="st-tag warn">Chưa có sao kê từ ngày ${M.vnDate(M.addDays(cov.data_until, 1))} (${gap} ngày)</span></li>`);
    }
    if (c.pending_imports > 0) facts.push(`<li><span class="st-tag warn">${c.pending_imports} lô chờ ghi</span></li>`);
    if (cov.unsigned_full_days > 0) {
      facts.push(`<li><span class="st-tag">${cov.unsigned_full_days} ngày đủ sao kê chưa ký số dư</span><a href="/doi-soat-ngay.html?account=${S.accountId}">Đối soát ngày ›</a></li>`);
    }
    facts.push(`<li class="st-small st-muted">Ngày ký số dư gần nhất: ${cov.last_signed_day ? M.vnDate(cov.last_signed_day) : 'chưa có'} · Số dư mở ${esc(M.money(c.opening.amount_minor))} đầu ngày ${M.vnDate(c.opening.as_of)}</li>`);
    return `<section class="nd-card" aria-label="Số dư"><div class="st-hero"><div><div class="st-label">Số dư theo sao kê</div>
      <div class="st-amount" id="st-balance">${esc(M.money(c.balance_minor))}</div><div class="st-muted st-small">${esc(until)}</div></div>
      <ul class="st-facts">${facts.join('')}</ul></div></section>`;
  }

  function templates() {
    const fixed = S.accounts.find(a => a.id === S.accountId)?.statement_template;
    const list = S.me.templates.filter(t => !fixed || t.id === fixed);
    if (!list.some(t => t.id === S.template)) S.template = list[0]?.id ?? null;
    return list;
  }

  function lineText(line) {
    const desc = line.description ? ` · ${line.description}` : '';
    return `Dòng ${line.line_no} · ${M.vnDate(line.booking_date)} · ${dirText(line.direction)} ${M.money(line.amount_minor)}${desc}`;
  }

  function txText(tx) {
    if (!tx) return 'giao dịch đã có';
    const desc = tx.description ? ` · ${tx.description}` : '';
    return `${M.vnDate(tx.booking_date)} · ${dirText(tx.direction)} ${M.money(tx.amount_minor)}${tx.bank_ref ? ` · mã ${tx.bank_ref}` : ''}${desc}`;
  }

  function questionsHtml(view, readOnly) {
    const { suspects, unmatched, pool } = M.questions(view);
    if (!suspects.length && !pool.length) return '';
    const off = readOnly || S.busy ? ' disabled' : '';
    const targets = new Map(Object.entries(S.choice.lines).filter(([, v]) => v !== 'new').map(([line, tx]) => [tx, line]));
    const items = suspects.map(({ line, candidates }) => {
      const picked = S.choice.lines[line.line_no];
      const radio = (value, label) => `<label><input type="radio" name="d-${line.line_no}" value="${value}" data-act="decide" data-line="${line.line_no}"
        data-f="d-${line.line_no}-${value}"${String(picked) === String(value) ? ' checked' : ''}${off}>${label}</label>`;
      const options = [radio('new', 'Đây là giao dịch mới')].concat(candidates.map(id => radio(id, `Trùng giao dịch đã có: ${esc(txText(S.known[id] ?? unmatched.find(u => u.transaction_id === id)))}`)));
      return `<li class="st-q${picked !== undefined ? ' done' : ''}"><div class="st-q-line">${esc(lineText(line))}</div>
        <div class="st-q-why">${candidates.length ? 'Sổ đã có giao dịch cùng ngày, cùng chiều, cùng số tiền. Xem file gốc rồi chọn:' : 'Có thể trùng giao dịch đã có. Chọn:'}</div>${options.join('')}</li>`;
    });
    // Giao dịch đã có trong kỳ mà file chưa nhận (lát 1, commit_import): là đích "trùng" của một dòng, hoặc giữ có lý do.
    const asks = new Set(M.keepAsks(view, S.choice));
    const kept = pool.map(id => {
      const tx = S.known[id] ?? unmatched.find(u => u.transaction_id === id);
      const head = `<div class="st-q-line">Giao dịch đã có trong sổ: ${esc(txText(tx))}</div>`;
      const by = targets.get(id);
      if (by) return `<li class="st-q done">${head}<div class="st-q-why">Đã ghép với dòng ${esc(by)} của file.</div></li>`;
      if (!asks.has(id)) return '';
      const why = unmatched.some(u => u.transaction_id === id) ? 'File mới không có giao dịch này.' : 'Dòng của file giống giao dịch này đã chọn là giao dịch mới, nên sổ giữ cả hai.';
      return `<li class="st-q">${head}<div class="st-q-why">${why} Nếu ngân hàng đã bỏ giao dịch thì bỏ lô và báo quản trị; nếu vẫn giữ, ghi lý do:</div>
        <textarea data-keep="${id}" data-f="keep-${id}" maxlength="500" aria-label="Lý do giữ giao dịch"${off}>${esc(S.choice.keep[id] ?? '')}</textarea></li>`;
    });
    return `<ol class="st-questions">${items.concat(kept).join('')}</ol>`;
  }

  function reviewHtml() {
    const v = S.review;
    if (!v || v.import.id !== S.reviewId) return '';
    const imp = v.import;
    const name = imp.file?.name ? ` · ${esc(imp.file.name)}` : '';
    const head = `<div class="st-review-head"><h3>Lô kỳ ${M.vnDate(imp.period_from)} – ${M.vnDate(imp.period_to)}${imp.last_day_complete ? '' : ' (ngày cuối chưa trọn)'}${name}</h3>
      <span class="st-tag ${imp.status === 'validated' ? 'warn' : imp.status === 'committed' ? 'ok' : ''}">${esc(M.IMPORT_STATUS[imp.status])}</span>
      <button type="button" class="nd-btn" data-act="close-review">Đóng</button></div>`;
    if (imp.status !== 'validated') {
      const c = imp.counts_at_preview;
      return `<div class="st-review" id="st-review">${head}<p class="st-counts">${c.rows} dòng lúc xem trước${imp.reason ? ` · Lý do: ${esc(imp.reason)}` : ''}.</p><div class="st-acts"></div></div>`;
    }
    const c = v.counts;
    const blockers = M.blockers(v);
    const warnings = M.warnings(v);
    const errors = v.lines.filter(l => l.class === 'error').slice(0, 20)
      .map(l => `<p>${esc(lineText(l))}: ${esc(M.LINE_ERROR[l.code] ?? l.code)}</p>`).join('');
    const { suspects, pool } = M.questions(v);
    const asks = [suspects.length ? `${suspects.length} dòng nghi trùng` : '', pool.length ? `${pool.length} giao dịch đã có cần xác nhận` : ''].filter(Boolean).join(' và ');
    const readOnly = !can('tien_review');
    const role = M.commitRole(v);
    const balanced = v.balance.opening_minor === null && v.balance.closing_minor === null
      ? '<p class="st-check">File không có số dư đầu, cuối: chưa kiểm được liền mạch với sổ; ký số dư ngày sẽ cần số dư từ ngân hàng.</p>'
      : v.balance.chain_breaks === 0 ? '<p class="st-check ok">Số dư đầu, cuối của file liền với sổ.</p>' : '';
    // Bảng đủ dòng chỉ dựng khi mở (lô tới 20000 dòng), và giữ trạng thái mở qua các lần vẽ lại (review lát 2).
    const rows = S.showAll ? v.lines.map(l => `<tr><td>${l.line_no}</td><td>${M.vnDate(l.booking_date)}</td><td>${dirText(l.direction)}</td>
      <td class="st-money">${esc(M.money(l.amount_minor))}</td><td>${esc(l.bank_ref ?? '')}</td>${v.raw_visible ? `<td class="st-desc">${esc(l.description ?? '')}</td>` : ''}
      <td><span class="st-tag ${l.class === 'error' ? 'bad' : l.class === 'suspect' ? 'warn' : l.class === 'new' ? 'ok' : ''}">${esc(M.CLASS[l.class])}</span></td></tr>`).join('') : '';
    const table = `<details class="st-more" id="st-all"${S.showAll ? ' open' : ''}><summary>Xem đủ ${c.rows} dòng</summary>${S.showAll ? `<div class="st-scroll"><table class="st-table"><thead><tr><th>Dòng</th><th>Ngày</th><th>Thu/Chi</th>
      <th class="st-money">Số tiền</th><th>Mã GD</th>${v.raw_visible ? '<th>Nội dung</th>' : ''}<th>Kết quả</th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}</details>`;
    const stop = blockers.length > 0 || !can(role) || S.busy;
    const acts = `<div class="st-acts">${can('tien_nhap') ? `<button type="button" class="nd-btn" data-act="reject"${S.busy ? ' disabled' : ''}>Bỏ lô</button>` : ''}
      <button type="button" class="nd-btn primary" data-act="commit"${stop ? ' disabled' : ''}>Ghi vào sổ</button></div>`;
    return `<div class="st-review" id="st-review">${head}
      <p class="st-counts">${c.rows} dòng: <b>${c.new}</b> mới · <b>${c.duplicate}</b> đã có trong sổ · <b>${c.suspect}</b> cần quyết · <b>${c.error}</b> lỗi</p>
      ${balanced}${blockers.length || errors ? `<div class="st-block">${blockers.map(b => `<p>${esc(b)}</p>`).join('')}${errors}</div>` : ''}
      ${warnings.length ? `<div class="st-warn">${warnings.map(w => `<p>${esc(w)}</p>`).join('')}</div>` : ''}
      ${questionsHtml(v, readOnly)}${role === 'tien_review' && readOnly ? `<p class="st-ro">Lô có ${asks}: người có vai đối chiếu mở lô này để quyết và ghi.</p>` : ''}
      ${role === 'tien_nhap' && !can('tien_nhap') ? '<p class="st-ro">Lô không có chỗ cần quyết; người có vai nhập bấm Ghi vào sổ.</p>' : ''}
      ${table}${acts}</div>`;
  }

  function importHtml() {
    if (!can('tien_nhap') && !can('tien_review')) return '';
    const list = templates();
    const pick = list.length > 1 ? `<select data-act="template" data-f="template" aria-label="Mẫu file">${list.map(t => `<option value="${esc(t.id)}"${t.id === S.template ? ' selected' : ''}>${esc(t.label)}</option>`).join('')}</select>` : '';
    const accept = list.map(t => t.extension).join(',');
    const button = can('tien_nhap') ? `<label class="nd-btn primary st-file">Chọn file sao kê<input type="file" data-act="upload" accept="${esc(accept)}"${!list.length || S.busy || S.card.opening === null ? ' disabled' : ''}></label>` : '';
    const hint = !list.length
      ? 'Chưa có mẫu đọc file sao kê của ngân hàng này. Mẫu có sau khi xem file mẫu tải từ ngân hàng.'
      : 'Dùng đúng file tải từ ngân hàng, không mở rồi lưu lại bằng Excel. Lô chỉ vào sổ khi bấm Ghi vào sổ.';
    const pending = S.imports.filter(i => i.status === 'validated' && i.id !== S.reviewId).map(i => `<div class="st-pending">
      <span class="st-tag warn">Chờ ghi</span><span>Kỳ ${M.vnDate(i.period_from)} – ${M.vnDate(i.period_to)} · ${i.counts.rows} dòng · ${esc(i.created?.actor ?? '')} ${M.stamp(i.created?.at)}${i.stale ? ' · sổ đã đổi, cần nhập lại' : ''}</span>
      <button type="button" class="nd-btn" data-act="open-import" data-id="${i.id}">Mở</button></div>`).join('');
    return `<section class="nd-card" aria-labelledby="st-import-title"><div class="nd-card-head"><h2 id="st-import-title">Nhập sao kê</h2>${pick}${button}</div>
      <div class="st-pad"><p class="st-hint">${esc(hint)}</p></div>${pending}${reviewHtml()}</section>`;
  }

  function importsHtml() {
    if (!S.imports.length) return '';
    const raw = can('tien_nhap') || can('tien_review');
    const rows = S.imports.slice(0, 20).map(i => {
      const acts = [];
      if (i.status === 'validated' && raw) acts.push(`<button type="button" class="nd-btn" data-act="open-import" data-id="${i.id}">Mở</button>`);
      if (i.file && raw) acts.push(`<button type="button" class="nd-btn" data-act="download-file" data-id="${i.file.id}">Tải file gốc</button>`);
      if (i.status === 'committed' && can('tien_review')) acts.push(`<button type="button" class="nd-btn" data-act="void" data-id="${i.id}"${S.busy ? ' disabled' : ''}>Hủy lô</button>`);
      return `<tr><td>${M.vnDate(i.period_from)} – ${M.vnDate(i.period_to)}</td><td><span class="st-tag ${i.status === 'committed' ? 'ok' : i.status === 'validated' ? 'warn' : ''}">${esc(M.IMPORT_STATUS[i.status])}</span></td>
        <td>${i.counts.rows} dòng · ${i.counts.new} mới</td><td class="st-small">${esc(i.created?.actor ?? '')} ${M.stamp(i.created?.at)}</td>
        <td class="st-small">${i.committed ? `${esc(i.committed.actor)} ${M.stamp(i.committed.at)}` : i.closed ? `${esc(i.closed.actor)} ${M.stamp(i.closed.at)}${i.reason ? ` · ${esc(i.reason)}` : ''}` : '—'}</td>
        <td><div class="nd-acts">${acts.join('')}</div></td></tr>`;
    }).join('');
    return `<section class="nd-card" aria-labelledby="st-imports-title"><div class="nd-card-head"><h2 id="st-imports-title">Các lần nhập</h2></div>
      <div class="st-scroll"><table class="st-table"><thead><tr><th>Kỳ</th><th>Trạng thái</th><th>Dòng</th><th>Nhập</th><th>Ghi / bỏ / hủy</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function detailHtml(d) {
    const t = d.transaction;
    const sources = d.sources.map(s => `<li>Lô ${M.vnDate(s.period_from)} – ${M.vnDate(s.period_to)}, dòng ${s.line_no}${s.role === 'duplicate_confirmed' ? ' (xác nhận trùng)' : ''}${s.import_status !== 'committed' ? ` · lô ${esc(M.IMPORT_STATUS[s.import_status]).toLowerCase()}` : ''}</li>`).join('');
    const allocations = d.allocations.length ? d.allocations.map(a => `<li>${esc(M.TARGET[a.target_kind]?.label ?? a.target_kind)}${Object.keys(a.target_ref).length ? ` (${esc(M.refText(a.target_ref))})` : ''}: ${esc(M.money(a.amount_minor))}${a.note ? ` · ${esc(a.note)}` : ''}</li>`).join('') : '<li>Chưa phân bổ.</li>';
    const history = d.history.map(h => `<li>${esc(h.by?.actor ?? '')} ${M.stamp(h.by?.at)}: ${h.after.length} dòng${h.reason ? ` · lý do: ${esc(h.reason)}` : ''}</li>`).join('');
    return `<div class="st-small"><p>Mã giao dịch trong sổ tiền: <b>#${t.id}</b> (dùng khi ghép chuyển nội bộ)</p><b>Nguồn</b><ul class="st-lines">${sources}</ul><b>Phân bổ</b><ul class="st-lines">${allocations}</ul>
      ${history ? `<b>Lịch sử phân bổ</b><ul class="st-lines">${history}</ul>` : ''}
      ${!t.voided ? `<p><a href="/doi-soat-ngay.html?account=${S.accountId}&date=${t.booking_date}">Phân bổ ở Đối soát ngày ${M.vnDate(t.booking_date)} ›</a></p>` : ''}</div>`;
  }

  function txHtml() {
    if (!S.tx) return '';
    const statuses = ['', 'unidentified', 'unapplied', 'partial', 'applied', 'unmatched', 'matched', 'voided'];
    const rows = S.tx.filter(t => !S.status || t.status === S.status);
    const cols = S.txDesc ? 7 : 6;
    const body = rows.length ? rows.map(t => {
      const open = S.openTx === t.id;
      const tr = `<tr class="st-row" data-tx="${t.id}" data-f="tx-${t.id}" aria-expanded="${open}" tabindex="0"><td>${M.vnDate(t.booking_date)}</td>
        <td class="st-money">${t.direction === 'in' ? esc(M.money(t.amount_minor)) : ''}</td><td class="st-money">${t.direction === 'out' ? esc(M.money(t.amount_minor)) : ''}</td>
        <td>${esc(t.bank_ref ?? '')}</td>${S.txDesc ? `<td class="st-desc">${esc(t.description ?? '')}</td>` : ''}
        <td><span class="st-tag ${t.status === 'applied' || t.status === 'matched' ? 'ok' : t.status === 'voided' ? '' : 'warn'}">${esc(M.STATUS[t.status])}</span></td>
        <td class="st-money">${t.voided ? '—' : esc(M.money(t.unallocated_minor))}</td></tr>`;
      return open && S.detail?.transaction.id === t.id ? `${tr}<tr class="st-detail"><td colspan="${cols}">${detailHtml(S.detail)}</td></tr>` : tr;
    }).join('') : `<tr><td colspan="${cols}" class="st-muted">Không có giao dịch trong tháng ${esc(S.month.split('-').reverse().join('/'))}${S.status ? ' với trạng thái này' : ''}.</td></tr>`;
    return `<section class="nd-card" aria-labelledby="st-tx-title"><div class="nd-card-head"><h2 id="st-tx-title">Giao dịch</h2>
      <div class="st-filter"><input type="month" data-act="month" data-f="month" value="${esc(S.month)}" max="${esc(S.card.today.slice(0, 7))}" aria-label="Tháng">
      <select data-act="status" data-f="status" aria-label="Trạng thái">${statuses.map(s => `<option value="${s}"${s === S.status ? ' selected' : ''}>${s ? esc(M.STATUS[s]) : 'Mọi trạng thái'}</option>`).join('')}</select>
      ${can('tien_review') ? '<button type="button" class="nd-btn" data-act="export">Xuất Excel tháng này</button>' : ''}</div></div>
      <div class="st-scroll"><table class="st-table"><thead><tr><th>Ngày</th><th class="st-money">Thu</th><th class="st-money">Chi</th><th>Mã GD</th>${S.txDesc ? '<th>Nội dung</th>' : ''}
      <th>Trạng thái</th><th class="st-money">Chưa phân bổ</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
  }

  function draw() {
    $('#st-account').innerHTML = S.me?.visible ? accountHtml() : '';
    const link = $('#st-to-days');
    if (S.accountId) link.href = `/doi-soat-ngay.html?account=${S.accountId}`;
    const root = $('#st-root');
    let html;
    if (S.off) html = empty('Sổ tiền chưa bật trên máy này.');
    else if (!S.me) return;
    else if (!S.me.visible) html = empty('Bạn chưa được cấp vai sổ tiền. Báo người quản trị sổ tiền cấp vai cho tài khoản đăng nhập của bạn.');
    else if (!S.accountId) html = empty('Chưa có tài khoản ngân hàng nào bạn được xem.');
    else if (!S.card) return;
    else html = cardHtml() + importHtml() + importsHtml() + txHtml();
    DoiXeChung.withFocus(() => { root.innerHTML = html; });
    net.drawToast();
  }

  // ---------- thao tác ----------
  function askReason(title, text, ok) {
    const dialog = $('#st-reason');
    $('#st-reason-title').textContent = title;
    $('#st-reason-text').textContent = text;
    $('#st-reason-ok').textContent = ok;
    const input = $('#st-reason-input');
    input.value = '';
    dialog.showModal();
    input.focus();
    return new Promise(resolve => {
      const onCancel = () => done(null);
      function done(value) {
        dialog.removeEventListener('click', onClick);
        dialog.removeEventListener('cancel', onCancel);
        dialog.close();
        resolve(value);
      }
      function onClick(event) {
        const act = event.target.closest('[data-act]')?.dataset.act;
        if (act === 'reason-cancel') done(null);
        if (act === 'reason-ok') {
          if (!M.clean(input.value)) { input.focus(); return; }
          done(M.clean(input.value));
        }
      }
      dialog.addEventListener('click', onClick);
      dialog.addEventListener('cancel', onCancel);
    });
  }

  async function download(url) {
    let response;
    try {
      response = await fetch(url, { cache: 'no-store' });
    } catch {
      net.bao('Mất kết nối, chưa tải được file.', 'err');
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      net.bao(body?.message ?? DoiXeChung.loiMayChu(response.status), 'err');
      return;
    }
    const blob = await response.blob();
    const header = response.headers.get('Content-Disposition') ?? '';
    const name = /filename\*=UTF-8''([^;]+)/.exec(header)?.[1];
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = name ? decodeURIComponent(name) : 'tep';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function upload(file) {
    if (!file) return;
    if (file.size > MAX_FILE) { net.bao('File quá 4 MB. Tải kỳ ngắn hơn từ ngân hàng.', 'err'); draw(); return; }
    const reader = new FileReader();
    reader.onerror = () => { net.bao('Không đọc được file trên máy này.', 'err'); draw(); };
    reader.onload = () => {
      const content = String(reader.result).split(',')[1] ?? '';
      net.ghi(`${API}/imports/preview`, { account_id: S.accountId, template: S.template, file_name: file.name, content_base64: content }, out => {
        if (out.same_file) {
          net.bao(`File này đã ghi vào sổ trước đây; không thêm giao dịch nào.`, 'warn');
          return;
        }
        S.reviewId = out.import_id;
        S.choice = { lines: {}, keep: {} };
        S.showAll = false;
        net.bao(`Đã đọc ${out.counts.rows} dòng. Xem lại rồi bấm Ghi vào sổ.`);
      });
    };
    reader.readAsDataURL(file);
  }

  function commit() {
    const built = M.commitBody(S.review, S.choice, S.known);
    if (built.error) { net.bao(built.error, 'err'); return; }
    net.ghi(`${API}/imports/commit`, built.body, out => {
      S.reviewId = null;
      S.review = null;
      net.bao(`Đã ghi vào sổ: ${out.created} giao dịch mới, ${out.confirmed} dòng đã có${out.kept ? `, giữ ${out.kept} giao dịch cũ` : ''}.`);
    });
  }

  async function reasonThen(title, text, ok, path, body, done) {
    const reason = await askReason(title, text, ok);
    if (reason === null) return;
    await net.ghi(path, { ...body, reason }, done);
  }

  document.addEventListener('change', event => {
    const el = event.target;
    const act = el.dataset.act;
    if (act === 'upload') upload(el.files?.[0]);
    if (act === 'account') {
      Object.assign(S, { accountId: Number(el.value), card: null, imports: [], tx: null, reviewId: null, review: null, openTx: null, detail: null, month: null });
      load();
    }
    if (act === 'template') S.template = el.value;
    if (act === 'month' && MONTH.test(el.value)) { S.month = el.value; S.openTx = null; load(); }
    if (act === 'status') { S.status = el.value; draw(); }
    if (act === 'decide') { S.choice.lines[el.dataset.line] = el.value === 'new' ? 'new' : Number(el.value); draw(); }
  });
  // <details> không nổi sự kiện toggle lên document: nghe ở pha bắt.
  document.addEventListener('toggle', event => {
    if (event.target.id === 'st-all' && event.target.open !== S.showAll) { S.showAll = event.target.open; draw(); }
  }, true);
  document.addEventListener('input', event => {
    const id = event.target.dataset.keep;
    if (id) S.choice.keep[id] = event.target.value;
  });
  document.addEventListener('click', event => {
    if (event.target.closest('dialog')) return;
    const el = event.target.closest('[data-act], tr.st-row, #refresh-data');
    if (!el) return;
    if (el.id === 'refresh-data') { load(); return; }
    if (el.matches('tr.st-row')) { toggleTx(Number(el.dataset.tx)); return; }
    const act = el.dataset.act;
    const id = Number(el.dataset.id);
    if (act === 'dong-toast') { S.toast = null; net.drawToast(); }
    if (act === 'open-import') { S.reviewId = id; S.choice = { lines: {}, keep: {} }; S.showAll = false; load(); }
    if (act === 'close-review') { S.reviewId = null; S.review = null; S.showAll = false; draw(); }
    if (act === 'commit') commit();
    if (act === 'reject') {
      reasonThen('Bỏ lô', 'Lô không vào sổ; file gốc vẫn được lưu. Nhập lại file khi cần.', 'Bỏ lô', `${API}/imports/reject`, { import_id: S.reviewId },
        () => { S.reviewId = null; S.review = null; net.bao('Đã bỏ lô.'); });
    }
    if (act === 'void') {
      reasonThen('Hủy lô đã ghi', 'Giao dịch chỉ có ở lô này sẽ bị hủy khỏi sổ (giao dịch có ở lô khác vẫn giữ). Không hủy được nếu giao dịch đang phân bổ hoặc thuộc ngày đã ký.',
        'Hủy lô', `${API}/imports/void`, { import_id: id }, out => net.bao(`Đã hủy lô: ${out.voided_transactions.length} giao dịch bị hủy, ${out.kept_transactions.length} giữ lại.`));
    }
    if (act === 'download-file') download(`${API}/files/${id}`);
    if (act === 'export') {
      const [from, to] = M.monthRange(S.month, S.card.today);
      download(`${API}/accounts/${S.accountId}/export.xlsx?from=${from}&to=${to}`);
    }
  });
  document.addEventListener('keydown', event => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches?.('tr.st-row')) { event.preventDefault(); toggleTx(Number(event.target.dataset.tx)); }
  });

  async function toggleTx(id) {
    if (S.openTx === id) { S.openTx = null; S.detail = null; draw(); return; }
    S.openTx = id;
    try {
      S.detail = await net.getJson(`${API}/transactions/${id}`);
    } catch (e) {
      S.openTx = null;
      net.bao(e.message, 'err');
    }
    draw();
  }

  load();
})();
