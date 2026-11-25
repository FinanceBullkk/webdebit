(() => {
  'use strict';
  // ZALO-THU-CHI-01 PR-2: trang Thu chi. Dữ liệu từ GET /api/v7/cash-chat, hỏi lại 5 giây một lần khi tab hiện; tổng, gom ngày,
  // lọc và câu trạng thái tính ở thu-chi-model.js, file này chỉ định dạng (ARCH-03). Tin chat không bao giờ ghi tiền.
  // Luồng 3 (PR-3): nút "Xử lý" ở mỗi khoản mở khung ngay dưới dòng: xác nhận, sửa số, gắn sổ/xe, loại (bắt buộc lý do), có trước → sau.
  // Ghi qua POST /api/v7/cash-chat/review, không đụng phiếu thu hay sổ Đội xe. Khung đang mở thì trang không vẽ lại dưới tay người dùng.
  const F = CongNoFormat;
  const M = ThuChiModel;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const root = $('thu-chi');
  // QUYEN-01 (sửa đổi 25/11/2026): người dùng xem cả trang; nút Xử lý (ghi kết luận, POST /api/v7/cash-chat/review) chỉ quản lý.
  const ADMIN = document.documentElement.dataset.role !== 'user';
  const POLL_MS = 5000;
  // `today`: ngày hôm nay theo giờ VN của máy chủ, giữ qua lần đổi khoảng (đổi khoảng thì `data` về null). Chưa hỏi được lần nào mới dùng đồng hồ máy.
  const state = { days: 7, filter: 'all', data: null, today: null, raw: '', fresh: new Set(), pending: null, fails: 0 };
  // Khung xử lý: `open` là khóa khoản đang mở, `mode` là việc đang làm (null, amount, target, not_cash), `key` là mã yêu cầu của lần ghi
  // (giữ qua lần bấm lại sau lỗi mạng để máy chủ không ghi hai lần), `form` là ô đang gõ.
  const edit = { open: null, mode: null, key: '', busy: false, form: {} };
  let targets = null;   // Promise danh sách sổ/xe/tài xế, chỉ hỏi khi mở ô gắn lần đầu
  let doneTimer = null;
  let pollTimer = null;
  let turn = 0;

  const hhmm = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false });
  const clock = ms => (ms == null ? '—' : hhmm.format(ms));
  const dayMonth = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const dayLabel = (iso, today) => (iso === today ? `Hôm nay ${dayMonth(iso)}` : iso === M.dayShift(today, -1) ? `Hôm qua ${dayMonth(iso)}` : dayMonth(iso));
  // Giờ của máy chủ là ISO có múi giờ: đọc bằng Date rồi đổi sang giờ Việt Nam, không cắt chuỗi.
  const stamp = (iso, today) => {
    const ms = Date.parse(iso ?? '');
    if (Number.isNaN(ms)) return '';
    const day = F.vnDay(ms);
    return `${day === today ? '' : `${dayMonth(day)} `}${hhmm.format(ms)}`;
  };
  const money = value => F.full(String(value));
  const count = n => n.toLocaleString('vi-VN');

  async function fetchData() {
    const today = state.today ?? F.vnDay(Date.now());
    const { from, to } = M.range(today, state.days);
    // Hỏi đủ mọi trạng thái, kể cả khoản đã loại: bộ lọc "Đã loại" lấy từ cùng một lần hỏi (model không đếm, không cộng khoản đó).
    const response = await fetch(`/api/v7/cash-chat?from=${from}&to=${to}&status=${M.STATUSES.join(',')}`, { cache: 'no-store', signal: AbortSignal.timeout(15_000) });
    if (!response.ok) throw Error('cash-chat');
    return response.text();
  }

  const SOURCE_NAMES = { receipt: 'phiếu thu', fleet: 'sổ Đội xe', directory: 'danh sách khách và xe', marks: 'dấu khách báo đã chuyển', links: 'danh sách nhóm gắn sổ' };
  // Tuổi dữ liệu Zalo: lấy từ nhịp tim của máy Zalo, không giả là mới. Máy im hoặc Zalo chưa mở thì có dòng cảnh báo riêng.
  function paintZalo(data) {
    // Cùng luật và cùng câu với trang Chat Zalo (CongNoFormat.zaloFreshness).
    const fresh = F.zaloFreshness(data.zalo, data.bundle_at, iso => stamp(iso, data.today));
    const label = $('zalo-at');
    label.textContent = fresh.label;
    label.classList.toggle('stale', fresh.stale);
    label.dataset.tip = data.last_message_at ? `Tin gần nhất lúc ${clock(data.last_message_at)}` : '';
    label.title = label.dataset.tip;
    const warn = $('zalo-warn');
    warn.textContent = fresh.warn;
    warn.hidden = !warn.textContent;
    // Nguồn sổ đọc lỗi: các khoản liên quan ghi "Chưa đối chiếu được", không kết luận chưa vào sổ.
    // File kết quả đọc ảnh hỏng thì khoản từ ảnh không hiện: nói rõ để không ai tưởng là không có ảnh chuyển khoản nào.
    const sources = $('source-warn');
    const failed = data.sources_failed ?? [];
    const skipped = Number.isInteger(data.conversations_skipped) ? data.conversations_skipped : 0;
    const names = failed.filter(code => code !== 'reads').map(code => SOURCE_NAMES[code] ?? code);
    sources.textContent = [names.length ? `Không đọc được ${names.join(', ')} lúc này. Các khoản liên quan ghi "Chưa đối chiếu được".` : '',
      failed.includes('reads') ? 'Không đọc được kết quả đọc ảnh chuyển khoản lúc này: khoản từ ảnh chưa hiện.' : '',
      // Máy chủ mỗi lần chỉ đọc 20 nhóm có tin mới nhất (MAX_CONVERSATIONS): nhóm thứ 21 trở đi không có khoản nào ở đây, nói rõ để không ai tưởng là chưa có thu chi.
      skipped > 0 ? `Còn ${count(skipped)} nhóm chat chưa được đọc ở đây (mỗi lần chỉ đọc 20 nhóm có tin mới nhất): khoản chuyển trong các nhóm đó chưa hiện.` : ''].filter(Boolean).join(' ');
    sources.hidden = !sources.textContent;
  }

  const fig = (kind, sum) => `<div class="tc-fig ${kind}"><b>${esc(money(sum[kind].vnd))}</b>`
    + `<small>${esc(M.KIND_LABEL[kind])} · ${count(sum[kind].n)} khoản${sum[kind].img ? `, ${count(sum[kind].img)} từ ảnh` : ''}</small></div>`;
  function card(title, sum) {
    const pill = (n, text, warn) => `<span class="tc-pill${n ? (warn ? ' warn' : '') : ' zero'}">${esc(text)}: ${count(n)}</span>`;
    return `<section class="tc-card" aria-label="${esc(title)}"><h2>${esc(title)}</h2><div class="tc-figs">${['thu', 'chi', 'ung'].map(kind => fig(kind, sum)).join('')}</div>`
      + `<div class="tc-flags">${pill(sum.missing, 'Chưa vào sổ', true)}${pill(sum.diff, 'Lệch số', true)}${sum.noAmount ? pill(sum.noAmount, 'Không đọc được số', false) : ''}</div></section>`;
  }

  function sumLine(sum) {
    const parts = ['thu', 'chi', 'ung'].filter(kind => sum[kind].n).map(kind => `${M.KIND_LABEL[kind]} ${money(sum[kind].vnd)}`);
    if (sum.missing) parts.push(`${count(sum.missing)} chưa vào sổ`);
    return parts.join(' · ');
  }

  function ledgerLink(item) {
    const ref = item.ledger_ref;
    if (!ref || !['RECORDED', 'AMOUNT_DIFF', 'SUGGEST'].includes(item.status)) return '';
    if (ref.kind === 'receipt') {
      const customer = ref.customer_id ?? item.target.id;
      if (customer == null) return '';
      const month = ref.date ? `&amp;month=${esc(ref.date.slice(0, 7))}` : '';
      return ` <a href="/so-khach-v7-live.html?customer=${encodeURIComponent(customer)}${month}">Mở sổ</a>`;
    }
    return ADMIN ? ' <a href="/doi-xe.html">Mở Đội xe</a>' : '';   // Đội xe chỉ quản lý
  }

  function thumbs(item) {
    if (!item.media.length) return '';
    const name = item.source === 'anh' ? 'Ảnh chuyển khoản' : 'Ảnh chứng';
    const shown = item.media.slice(0, 2).map(media => `<a href="/api/v7/zalo/media/${esc(media.id)}" target="_blank" rel="noopener" aria-label="Xem ${name.toLowerCase()}">`
      + `<img src="/api/v7/zalo/media/${esc(media.id)}" alt="${name}" loading="lazy"></a>`).join('');
    const more = item.media.length > 2 ? `<span>+${item.media.length - 2}</span>` : '';
    return `<div class="tc-thumbs">${shown}${more}</div>`;
  }

  // Giờ giao dịch đọc từ ảnh, theo giờ Việt Nam (giờ không ghi múi thì đã là giờ Việt Nam). Cùng ngày với tin thì chỉ ghi giờ;
  // chỉ đọc ra ngày mà trùng ngày tin thì không ghi gì.
  function txnLabel(value, day) {
    if (!value) return '';
    let iso = value.slice(0, 10);
    let time = '';
    const local = /^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2})(?::\d{2})?$/.exec(value);
    if (local) time = `${local[1]}:${local[2]}`;
    else if (value.includes('T')) {
      const ms = Date.parse(value);
      if (Number.isNaN(ms)) return '';
      iso = F.vnDay(ms);
      time = hhmm.format(ms);
    }
    if (!time) return iso === day ? '' : `ngày ${dayMonth(iso)}`;
    return iso === day ? time : `${time} ${dayMonth(iso)}`;
  }
  // Khoản từ ảnh không có chữ: cột nội dung ghi giờ giao dịch rồi ngân hàng máy đọc được, để so với phiếu. Giờ đứng trước vì
  // ô hẹp bị cắt ở cuối dòng: mất tên ngân hàng còn hơn mất giờ.
  function imageLine(item) {
    const when = txnLabel(item.image?.txn_time, item.day);
    return [when ? `Giao dịch ${when}` : 'Ảnh chuyển khoản', item.image?.bank].filter(Boolean).join(' · ');
  }

  const TARGET = M.TARGET_LABEL;
  const targetText = target => `${TARGET[target.kind] ?? ''} ${target.label ?? ''}`.trim() || '—';
  // Lần xử lý gần nhất, hiện ngay trong ô trạng thái: ai làm, lúc nào, bao nhiêu lần.
  function reviewLine(item) {
    const last = M.reviewSummary(item);
    if (!last) return '';
    const who = [last.by, last.at ? stamp(last.at, state.data?.today) : ''].filter(Boolean).join(' · ');
    return `<small class="tc-rev">${esc(last.what)}${who ? ` · ${esc(who)}` : ''}${last.times > 1 ? ` · ${count(last.times)} lần` : ''}</small>`;
  }

  function row(item) {
    const status = M.statusText(item);
    const key = M.keyOf(item);
    const text = item.source === 'anh' ? imageLine(item) : item.text;
    const open = item.conversation_id
      ? `<a class="tc-open" href="/zalo-chat.html?c=${encodeURIComponent(item.conversation_id)}${item.message_id ? `&amp;m=${encodeURIComponent(item.message_id)}` : ''}&amp;from=thu-chi">Mở tin</a>` : '';
    const can = M.reviewable(item, state.data.items);
    const act = ADMIN && can.ok ? `<button type="button" class="tc-act" data-act="open" data-k="${esc(key)}" aria-expanded="${edit.open === key}">Xử lý</button>` : '';
    const note = [status.note, can.ok || item.source === 'mark' ? '' : can.why].filter(Boolean).join(' ');
    const amount = item.amount_vnd == null ? '<span class="dash">—</span>' : esc(money(item.amount_vnd));
    const from = item.amount_from === 'anh' ? 'đọc từ ảnh' : item.amount_from === 'sua' ? 'đã sửa tay' : '';
    // Khoản nằm ở ngày giao dịch (ảnh cũ gửi lại) hoặc ngày khách báo (dấu): tin gửi ngày khác thì ghi cả ngày tin.
    const sentDay = item.sent_at == null ? null : F.vnDay(item.sent_at);
    const time = sentDay && sentDay !== item.day ? `${dayMonth(sentDay)} ${clock(item.sent_at)}` : clock(item.sent_at);
    return `<div class="tc-row${state.fresh.has(key) ? ' is-new' : ''}${edit.open === key ? ' is-open' : ''}" data-status="${esc(item.status)}" data-source="${esc(item.source)}" data-k="${esc(key)}">`
      + `<span class="tc-time">${esc(time)}</span>`
      + `<div class="tc-who"><b title="${esc(item.sender_name ?? '')}">${esc(item.sender_name ?? 'Không rõ tên')}</b><small title="${esc(item.conversation_name ?? '')}">${esc(item.conversation_name ?? '')}${item.source === 'mark' ? ' · dấu khách báo' : ''}</small></div>`
      + `<span class="tc-kind-cell"><span class="tc-kind ${esc(item.direction)}">${esc(M.KIND_LABEL[item.direction])}</span></span>`
      + `<span class="tc-amt">${amount}${from ? `<small class="tc-src">${from}</small>` : ''}</span>`
      + `<div class="tc-target">${esc(targetText(item.target))}${item.target_from === 'sua' ? ' <small class="tc-src">gắn tay</small>' : ''}<span class="tc-text" title="${esc(text)}">${esc(text)}</span></div>`
      + `<div class="tc-status ${status.tone}"><b>${esc(status.text)}</b>${note ? `<small>${esc(note)}</small>` : ''}${reviewLine(item)}${ledgerLink(item)}</div>`
      + `<div class="tc-side">${thumbs(item)}${act}${open}</div></div>`
      + (edit.open === key ? panel(item) : '');
  }

  // ---- Khung xử lý (Luồng 3) ----
  const openItem = () => (edit.open && state.data && !state.data.unavailable ? state.data.items.find(item => M.keyOf(item) === edit.open) ?? null : null);
  const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

  function panel(item) {
    const buttons = M.actions(item).map(action => {
      const pressed = ['amount', 'target', 'not_cash'].includes(action) ? ` aria-pressed="${edit.mode === action}"` : '';
      // Một nút chính mỗi lúc: đang gõ sửa số, gắn hay lý do thì nút Lưu của ô là chính, "Đúng, xác nhận" lùi về nút thường.
      const tone = (action === 'confirm' && !edit.mode) || action === 'restore' ? ' primary' : action === 'not_cash' ? ' quiet-danger' : '';
      return `<button type="button" class="btn${tone}" data-act="${action}"${pressed}${edit.busy ? ' disabled' : ''}>${esc(M.ACTION_LABEL[action])}</button>`;
    }).join('');
    const hint = item.status === 'NOT_CASH' ? 'Đưa lại thì khoản được đếm, cộng tổng và đối chiếu như trước.'
      : 'Xác nhận, sửa số hay gắn đối tượng chỉ ghi vào trang này: không ghi phiếu thu hay dòng chi. Tin gốc trong Zalo giữ nguyên.';
    return `<div class="tc-panel" role="group" aria-label="Xử lý khoản ${esc(M.KIND_LABEL[item.direction].toLowerCase())} ${esc(M.money(item.amount_vnd))}">`
      + `<div class="tc-acts">${buttons}<button type="button" class="btn tc-close" data-act="close">Đóng</button></div>`
      + `<div class="tc-form">${form(item) || `<p class="tc-hint">${esc(hint)}</p>`}</div>`
      + `<p class="tc-perr" role="alert"${edit.error ? '' : ' hidden'}>${esc(edit.error ?? '')}</p></div>`;
  }

  function form(item) {
    if (edit.mode === 'amount') {
      return `<label class="tc-field">Số đúng<input id="tc-amount" inputmode="numeric" autocomplete="off" maxlength="20" value="${esc(edit.form.amount ?? '')}" placeholder="Ví dụ 4.500.000"></label>`
        + foot(amountPreview(item), 'Lưu số', 'primary', item);
    }
    if (edit.mode === 'not_cash') {
      return `<label class="tc-field wide">Lý do (bắt buộc)<textarea id="tc-reason" rows="2" maxlength="500" placeholder="Ví dụ: tin hỏi giá, không phải tiền đã chuyển">${esc(edit.form.reason ?? '')}</textarea></label>`
        + foot('Khoản sẽ ẩn khỏi danh sách, không đếm và không cộng vào tổng. Xem lại hoặc đưa lại ở bộ lọc "Đã loại".', 'Loại khoản', 'danger', item);
    }
    if (edit.mode === 'target') {
      const kinds = M.targetKinds(item.direction);
      const kind = edit.form.kind ?? kinds[0];
      const choose = kinds.length > 1 ? `<div class="tc-kinds" role="radiogroup" aria-label="Loại đối tượng">${kinds.map(one =>
        `<button type="button" class="tc-chip" role="radio" data-kind="${one}" aria-checked="${one === kind}">${esc(TARGET[one])}</button>`).join('')}</div>` : '';
      return `${choose}<label class="tc-field">Tìm ${esc(TARGET[kind].toLowerCase())}<input id="tc-q" autocomplete="off" maxlength="80" value="${esc(edit.form.query ?? '')}"`
        + ` placeholder="${kind === 'xe' ? 'Gõ biển số' : kind === 'so' ? 'Gõ tên sổ' : 'Gõ tên tài xế'}"></label>`
        + `<div class="tc-opts" id="tc-opts" role="listbox" aria-label="Chọn ${esc(TARGET[kind].toLowerCase())}">${options(kind)}</div>`
        + foot(targetPreview(item), 'Lưu đối tượng', 'primary', item);
    }
    return '';
  }

  // Hàng cuối của khung: câu trước → sau (hay lời nhắc) và nút Lưu cạnh nhau, để thấy cả hai trước khi bấm.
  const foot = (preview, label, tone, item) => `<div class="tc-foot"><p class="tc-preview" id="tc-preview">${preview}</p>`
    + `<button type="button" class="btn ${tone}" data-act="save"${saveable(item) ? '' : ' disabled'}>${esc(label)}</button></div>`;

  // Trước → sau, hiện trước khi bấm Lưu. Số không hợp lệ thì nói rõ, không đoán.
  function amountPreview(item) {
    const raw = edit.form.amount ?? '';
    const next = M.parseAmount(raw);
    const before = item.amount_vnd == null ? 'chưa có số' : money(item.amount_vnd);
    if (!raw.trim()) return `Số đang có: ${esc(before)}. Gõ số đúng, chỉ chữ số.`;
    if (!next) return '<span class="bad">Chỉ gõ chữ số (có thể có dấu chấm ngăn nghìn), lớn hơn 0. Không gõ "tr" hay "k".</span>';
    if (item.amount_vnd != null && String(item.amount_vnd) === next) return 'Bằng số đang có, không cần sửa.';
    return `Số: <s>${esc(before)}</s> → <b>${esc(money(next))}</b>`;
  }
  function targetPreview(item) {
    const chosen = edit.form.chosen;
    if (!chosen) return `Đối tượng đang có: ${esc(targetText(item.target))}. Chọn một dòng ở trên.`;
    if (chosen.kind === item.target.kind && chosen.id === item.target.id) return 'Đúng đối tượng đang có, không cần gắn lại.';
    return `Đối tượng: <s>${esc(targetText(item.target))}</s> → <b>${esc(targetText(chosen))}</b>`;
  }
  function saveable(item) {
    if (edit.busy) return false;
    if (edit.mode === 'amount') {
      const next = M.parseAmount(edit.form.amount);
      return Boolean(next) && (item.amount_vnd == null || String(item.amount_vnd) !== next);
    }
    if (edit.mode === 'target') {
      const chosen = edit.form.chosen;
      return Boolean(chosen) && !(chosen.kind === item.target.kind && chosen.id === item.target.id);
    }
    if (edit.mode === 'not_cash') return Boolean((edit.form.reason ?? '').trim());
    return false;
  }

  function options(kind) {
    if (edit.form.list === undefined) return '<p class="tc-hint">Đang tải danh sách…</p>';
    if (edit.form.list === null) return '<p class="tc-hint bad">Không tải được danh sách sổ và xe. Đóng rồi mở lại để thử lại.</p>';
    const rows = edit.form.list[kind] ?? [];
    const found = M.searchTargets(rows, edit.form.query ?? '');
    const note = edit.form.list.failed ? '<p class="tc-hint bad">Danh sách có thể thiếu: một phần chưa đọc được lúc này.</p>' : '';
    if (!found.length) return `${note}<p class="tc-hint">${rows.length ? 'Không có tên nào khớp.' : 'Danh sách trống.'}</p>`;
    return note + found.map(row => {
      const on = edit.form.chosen?.kind === kind && edit.form.chosen.id === row.id;
      return `<button type="button" class="tc-opt" role="option" data-pick="${esc(row.id)}" aria-selected="${on}">${esc(row.label)}</button>`;
    }).join('');
  }

  // Vẽ lại riêng khung đang mở (đổi việc, tải xong danh sách, báo lỗi), không đụng phần còn lại của trang.
  function repaintPanel(focus) {
    const item = openItem();
    const old = root.querySelector('.tc-panel');
    if (!item || !old) return;
    old.outerHTML = panel(item);
    if (focus) root.querySelector(`.tc-panel ${focus}`)?.focus({ preventScroll: true });
    reveal();
  }
  // Gõ phím trong ô: chỉ cập nhật dòng trước → sau, danh sách chọn và nút Lưu, giữ con trỏ trong ô.
  function refreshForm() {
    const item = openItem();
    if (!item) return;
    const preview = $('tc-preview');
    if (preview && edit.mode !== 'not_cash') preview.innerHTML = edit.mode === 'amount' ? amountPreview(item) : targetPreview(item);
    if (edit.mode === 'target' && $('tc-opts')) $('tc-opts').innerHTML = options(edit.form.kind ?? M.targetKinds(item.direction)[0]);
    const save = root.querySelector('.tc-panel [data-act="save"]');
    if (save) save.disabled = !saveable(item);
  }

  // Khung mở hay đổi việc: kéo vừa đủ để thấy hết khung (nút Lưu không nằm dưới mép màn).
  const reveal = () => root.querySelector('.tc-panel')?.scrollIntoView({ block: 'nearest' });

  function openPanel(key) {
    if (edit.open === key) return closePanel();   // bấm lại nút Xử lý của dòng đang mở: đóng
    Object.assign(edit, { open: key, mode: null, key: newKey(), busy: false, form: {}, error: null });
    render();
    root.querySelector('.tc-panel .btn')?.focus({ preventScroll: true });
    reveal();
    return undefined;
  }
  function closePanel() {
    const key = edit.open;
    Object.assign(edit, { open: null, mode: null, busy: false, form: {}, error: null });
    if (state.pending) apply(state.pending);
    else render();
    if (key) root.querySelector(`.tc-act[data-k="${CSS.escape(key)}"]`)?.focus();
  }

  function setMode(mode) {
    const item = openItem();
    if (!item) return;
    Object.assign(edit, { mode: edit.mode === mode ? null : mode, key: newKey(), form: {}, error: null });
    if (edit.mode === 'target') {
      edit.form.kind = item.target.kind && M.targetKinds(item.direction).includes(item.target.kind) ? item.target.kind : M.targetKinds(item.direction)[0];
      loadTargets();
    }
    repaintPanel({ amount: '#tc-amount', target: '#tc-q', not_cash: '#tc-reason' }[edit.mode] ?? `[data-act="${mode}"]`);
  }

  function loadTargets() {
    targets ??= fetch('/api/v7/cash-chat/targets', { cache: 'no-store', signal: AbortSignal.timeout(15_000) })
      .then(response => (response.ok ? response.json() : Promise.reject(Error('targets'))));
    const mine = edit.key;
    // Danh sách về thì khung cao thêm: kéo lại cho thấy nút Lưu.
    targets.then(list => { if (edit.key === mine) { edit.form.list = list; refreshForm(); reveal(); } },
      () => { targets = null; if (edit.key === mine) { edit.form.list = null; refreshForm(); } });
  }

  async function post(body) {
    const response = await fetch('/api/v7/cash-chat/review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      signal: AbortSignal.timeout(20_000) });
    let data = null;
    try { data = await response.json(); } catch { /* lỗi không có thân: dùng câu chung */ }
    if (!response.ok) {
      const error = Error(data?.message || '');
      error.code = data?.error;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function showDone(html) {
    const done = $('done');
    clearTimeout(doneTimer);
    done.innerHTML = html;
    done.hidden = !html;
    if (html) doneTimer = setTimeout(() => { done.hidden = true; done.innerHTML = ''; }, 12_000);
  }

  // Ghi một việc. `action` là confirm/restore (bấm thẳng) hoặc việc của ô đang mở. Thành công thì đóng khung, báo một dòng và hỏi lại ngay
  // (máy chủ đã bỏ kết quả đang giữ). Lỗi mạng giữ mã yêu cầu: bấm lại không ghi hai lần.
  async function save(action) {
    const item = openItem();
    if (!item || edit.busy) return;
    const body = { message_id: item.message_id, action: action === 'restore' ? 'confirm' : action, request_id: edit.key };
    if (action === 'amount') body.value = M.parseAmount(edit.form.amount);
    if (action === 'target') body.value = { kind: edit.form.chosen.kind, id: edit.form.chosen.id };
    if (action === 'not_cash') body.reason = edit.form.reason.trim();
    edit.busy = true;
    edit.error = null;
    repaintPanel();
    try {
      await post(body);
      const what = M.KIND_LABEL[item.direction].toLowerCase();
      const of = `khoản ${what} ${M.money(item.amount_vnd)}${item.sender_name ? ` của ${item.sender_name}` : ''}`;
      const message = {   // hàm, không phải chuỗi: chỉ dựng câu của việc vừa làm (ô gắn chưa chọn thì không có `chosen`)
        confirm: () => `Đã xác nhận ${of}.`,
        restore: () => `Đã đưa lại ${of} vào thu chi.`,
        amount: () => `Đã sửa số: ${M.money(item.amount_vnd)} → ${M.money(body.value)}.`,
        target: () => `Đã gắn ${of} vào ${targetText(edit.form.chosen)}.`,
        not_cash: () => `Đã loại ${of}. Xem lại ở bộ lọc "Đã loại".`,
      }[action]();
      const undo = action === 'not_cash' ? ` <button type="button" class="btn" data-undo="${esc(item.message_id)}">Hoàn tác</button>` : '';
      Object.assign(edit, { open: null, mode: null, busy: false, form: {}, error: null });
      showDone(`${esc(message)}${undo}`);
      $('new-note').textContent = message;
      state.raw = '';
      await load({ force: true });
    } catch (error) {
      edit.busy = false;
      if (error.code === 'IDEMPOTENCY_CONFLICT') {
        // Lần bấm trước (chưa rõ kết quả) đã ghi nội dung cũ dưới mã này: không ghi đè, tải lại để người dùng xem rồi làm tiếp bằng mã mới.
        edit.key = newKey();
        edit.error = 'Lần bấm trước đã được ghi với nội dung cũ. Trang đã tải lại: xem khoản rồi làm tiếp nếu cần.';
        state.raw = '';
        load({ force: true });
      } else {
        edit.error = error.status ? (error.message || 'Không lưu được.') : 'Không chắc đã lưu (mất mạng hoặc máy chủ chậm). Bấm lại: máy không ghi hai lần.';
      }
      repaintPanel('.tc-perr');
    }
  }

  async function undoDrop(messageId) {
    const done = $('done');
    done.querySelector('[data-undo]')?.setAttribute('disabled', '');
    try {
      await post({ message_id: messageId, action: 'confirm', request_id: newKey() });
      showDone('Đã đưa khoản lại vào thu chi.');
      state.raw = '';
      await load({ force: true });
    } catch (error) {
      showDone(esc(error.status ? error.message || 'Không hoàn tác được.' : 'Không chắc đã hoàn tác. Mở bộ lọc "Đã loại" để xem.'));
    }
  }

  function render() {
    const data = state.data;
    if (data.unavailable) {
      root.innerHTML = '<p class="empty">Máy chủ chưa có dữ liệu chat Zalo. Khi nhóm Zalo đã chọn được đưa lên máy chủ thì thu chi hiện ở đây.</p>';
      return;
    }
    const all = data.items;
    const keepFocus = document.activeElement?.dataset?.f ?? null;
    const counts = M.counts(all);
    const shown = M.groupByDay(M.filterItems(all, state.filter));
    const range = state.days === 7 ? '7 ngày' : `${state.days} ngày`;
    const optional = { noamount: true, notcash: true };   // chip chỉ hiện khi có khoản (hoặc đang chọn)
    const filters = M.FILTERS.filter(filter => !optional[filter.id] || counts[filter.id] || state.filter === filter.id)
      .map(filter => `<button type="button" class="tc-chip" data-f="${filter.id}" aria-pressed="${filter.id === state.filter}">${esc(filter.label)}<b>${count(counts[filter.id])}</b></button>`).join('');
    const empty = !all.some(item => item.status !== 'NOT_CASH') && state.filter !== 'notcash'
      ? `<p class="empty">Chưa có khoản thu chi nào trong ${range}. Ở đây hiện ảnh chuyển khoản khách gửi mà máy đọc được, và tin bắt đầu bằng thu, chi hoặc ứng kèm số tiền, ví dụ: thu 50tr Khách A.</p>`
      : !shown.length ? '<p class="empty">Không có khoản nào trong bộ lọc này.</p>' : '';
    // Ảnh cũ gửi lại có giao dịch trước khoảng đang xem: không cộng vào khoảng này, nói rõ số ảnh để không ai tưởng bị sót.
    const before = data.images_before ? `<p class="tc-note">${count(data.images_before)} ảnh chuyển khoản gửi trong ${range} là giao dịch trước đó, không cộng vào tổng.</p>` : '';
    root.innerHTML = `<div class="tc-band">${card('Hôm nay', M.summarize(all.filter(item => item.day === data.today)))}${card(`${range} gần nhất`, M.summarize(all))}</div>`
      + `<div class="tc-filters" role="group" aria-label="Lọc khoản">${filters}</div>${before}${empty}`
      + shown.map(group => `<section class="tc-day" aria-label="${esc(dayLabel(group.day, data.today))}"><header><h3>${esc(dayLabel(group.day, data.today))}</h3>`
        + `<span class="sums">${esc(sumLine(group.sum))}</span></header>${group.rows.map(row).join('')}</section>`).join('');
    if (keepFocus) root.querySelector(`[data-f="${keepFocus}"]`)?.focus();
    // Khoản đang mở không còn trên màn (lọc khác, người khác vừa loại): đóng khung, không giữ trang ở trạng thái "đang sửa".
    if (edit.open && !root.querySelector('.tc-panel')) Object.assign(edit, { open: null, mode: null, busy: false, form: {}, error: null });
  }

  // Đang đọc (cuộn xuống, tiêu điểm nằm trong danh sách, hoặc khung xử lý đang mở) thì không vẽ lại dưới tay người dùng: giữ bản mới ở
  // `pending` và hiện nút.
  const inList = () => Boolean(document.activeElement?.closest?.('.tc-day'));
  const reading = () => window.scrollY > 120 || inList() || edit.open !== null;

  function showPill() {
    const pill = $('new-pill');
    pill.hidden = !state.pending;
    if (!state.pending) return;
    const added = M.newKeys(state.data.items, state.pending.data.items ?? []).length;
    pill.textContent = added ? `Có ${count(added)} khoản mới, bấm để xem` : 'Có cập nhật mới, bấm để xem';
    $('new-note').textContent = pill.textContent;
  }

  function apply(next) {
    // Chỉ so khoản mới khi cả hai bản đều có dữ liệu: hồi từ "thiếu gói" không tô mọi khoản là mới.
    const before = state.data && !state.data.unavailable ? state.data.items : null;
    const added = before && !next.data.unavailable ? M.newKeys(before, next.data.items) : [];
    state.raw = next.text;
    state.data = next.data;
    state.pending = null;
    state.fresh = new Set(added);
    $('new-note').textContent = added.length ? `Có ${count(added.length)} khoản mới` : '';
    $('new-pill').hidden = true;
    render();
    state.fresh = new Set();   // tô nền chỉ một lần: bấm chip lọc vẽ lại không tô lại
  }

  async function load({ force = false } = {}) {
    const mine = ++turn;
    try {
      const text = await fetchData();
      if (mine !== turn) return;
      $('error').hidden = true;
      state.fails = 0;
      const data = JSON.parse(text);
      if (typeof data.today === 'string') state.today = data.today;
      paintZalo(data);
      if (text === state.raw) {
        state.pending = null;
        showPill();
        return;
      }
      const next = { text, data };
      if (!force && state.data && !state.data.unavailable && !data.unavailable && reading()) {
        state.pending = next;
        showPill();
        return;
      }
      apply(next);
    } catch {
      if (mine !== turn) return;
      state.fails += 1;
      const error = $('error');
      error.innerHTML = state.data
        ? 'Không cập nhật được. Số đang hiện là lần tải trước.'
        : `${esc(F.loadError('thu chi'))} <button type="button" class="btn" id="retry">Thử lại</button>`;
      error.hidden = false;
      $('retry')?.addEventListener('click', () => { load({ force: true }).then(schedule); });
      if (!state.data) root.innerHTML = '';
    }
  }

  // Nhịp 5 giây; lỗi liên tiếp thì giãn dần (10, 20, rồi 30 giây) để máy chủ đang chậm không bị hỏi dồn.
  function schedule() {
    clearTimeout(pollTimer);
    pollTimer = document.hidden ? null : setTimeout(async () => { await load(); schedule(); }, POLL_MS * Math.min(2 ** state.fails, 6));
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(pollTimer);
    if (!document.hidden) load().then(schedule);   // tab hiện lại: hỏi ngay một lượt rồi theo nhịp 5 giây; tab ẩn thì ngừng
  });
  root.addEventListener('click', event => {
    const chip = event.target.closest('[data-f]');
    if (chip) {
      state.filter = chip.dataset.f;
      render();
      if (!edit.open && state.pending) apply(state.pending);   // khung vừa đóng vì khoản bị lọc mất: nhận bản mới đang chờ
      return;
    }
    const act = event.target.closest('[data-act]');
    const pick = event.target.closest('[data-pick]');
    const kind = event.target.closest('[data-kind]');
    if (act) {
      const action = act.dataset.act;
      if (action === 'open') openPanel(act.dataset.k);
      else if (action === 'close') closePanel();
      else if (action === 'confirm' || action === 'restore') save(action);
      else if (action === 'save') save(edit.mode);
      else setMode(action);
    } else if (pick && edit.form.list) {
      const kindNow = edit.form.kind;
      const found = (edit.form.list[kindNow] ?? []).find(row => String(row.id) === pick.dataset.pick);
      if (found) edit.form.chosen = { kind: kindNow, id: found.id, label: found.label };
      refreshForm();
      root.querySelector(`.tc-panel [data-pick="${CSS.escape(pick.dataset.pick)}"]`)?.focus();
    } else if (kind && edit.form.kind !== kind.dataset.kind) {
      Object.assign(edit.form, { kind: kind.dataset.kind, chosen: null, query: '' });
      repaintPanel(`[data-kind="${kind.dataset.kind}"]`);
    }
  });
  // Gõ trong ô của khung: lưu vào `edit.form` (vẽ lại khung vẫn giữ chữ), cập nhật trước → sau và nút Lưu.
  root.addEventListener('input', event => {
    const field = { 'tc-amount': 'amount', 'tc-q': 'query', 'tc-reason': 'reason' }[event.target.id];
    if (!field) return;
    edit.form[field] = event.target.value;
    edit.error = null;
    const error = root.querySelector('.tc-perr');
    if (error) error.hidden = true;
    refreshForm();
  });
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && edit.open && !edit.busy) closePanel();
    // Enter trong ô số thì lưu luôn, như bấm nút (khi số hợp lệ và khác số đang có).
    if (event.key === 'Enter' && event.target.id === 'tc-amount') {
      event.preventDefault();
      if (saveable(openItem())) save('amount');
    }
  });
  $('done').addEventListener('click', event => {
    const undo = event.target.closest('[data-undo]');
    if (undo) undoDrop(undo.dataset.undo);
  });
  $('new-pill').addEventListener('click', () => {
    if (state.pending) apply(state.pending);
    window.scrollTo({ top: 0 });
  });
  // Cuộn về đầu trang và tiêu điểm không còn trong danh sách thì nhận bản mới luôn, không cần bấm nút.
  window.addEventListener('scroll', () => { if (state.pending && !reading()) apply(state.pending); }, { passive: true });
  $('range').addEventListener('change', event => {
    state.days = Number(event.target.value);
    state.data = null;   // khoảng khác thì không so với bản cũ để tìm khoản mới
    state.raw = '';
    state.pending = null;
    $('new-pill').hidden = true;
    root.innerHTML = '<p class="loading">Đang tải thu chi…</p>';
    load({ force: true });
  });
  $('refresh-data').addEventListener('click', () => { state.raw = ''; load({ force: true }); });

  load({ force: true }).then(schedule);
})();
