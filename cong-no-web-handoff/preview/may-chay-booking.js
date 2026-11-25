/* Khối "Kiểm sổ với booking" của tab Máy chạy. Chỉ xem: đọc /api/v7/machine/booking, không có lệnh ghi.
 * Hai phía so, chọn bằng nút trên đầu khối: "Sổ web" (DU-CHUYEN-01, tiêu chí số 1: web đủ chuyến booking; mặc định) và "Sheet sổ nợ"
 * (KIEM-BOOKING-01). API cũ chưa có `web_check` thì chỉ có phía Sheet, không hiện nút chọn.
 * Thứ tự theo câu chủ sổ hỏi: lượt kiểm gần nhất có tin được không, rồi bốn nhóm đụng tiền, rồi ba nhóm chỉ để biết. Bấm nhóm thì mở
 * danh sách ngay dưới. Chưa có kết quả, kết quả cũ hay lượt lỗi thì nói rõ, không bao giờ hiện như "không có gì lệch".
 * Nhóm "tháng này" tách hai khi API đã so với sổ web (`recent_web: 'checked'`): web chưa có (cần xem) và máy đã đưa vào web, chỉ
 * chờ Sheet ghi. Đọc sổ web lỗi thì giữ một nhóm như trước. */
(() => {
  'use strict';
  const F = CongNoFormat, esc = F.esc, $ = id => document.getElementById(id);
  const REFRESH = 5 * 60 * 1000, FETCH_TIMEOUT = 15000;
  const GROUPS = [
    { key: 'dup', name: 'Nghi tính hai lần', money: true, about: 'Hai dòng có tiền cùng là một chuyến booking.' },
    { key: 'missing', name: 'Booking có, sổ chưa tính', money: true, about: 'Chuyến đã đi theo booking mà chưa sổ nào tính tiền.' },
    { key: 'other', name: 'Sổ khác khách booking', money: true, about: 'Chuyến biển mà chủ hàng trên booking khác khách của sổ.' },
    { key: 'nosource', name: 'Trên sổ, booking không có', money: true, about: 'Sổ tính tiền một container mà booking không có.' },
    { key: 'date', name: 'Lệch ngày', money: false, about: 'Cùng chuyến, ngày trên sổ khác booking. Không đổi tiền.' },
    { key: 'nodate', name: 'Sổ thiếu ngày', money: false, about: 'Dòng sổ không có ngày, booking có. Không đổi tiền.' },
    { key: 'recent', name: 'Tháng này chưa lên sổ', money: false, about: 'Chuyến tháng này có trong booking, sổ có thể chưa kịp ghi.' },
    // Không phải nhóm của dòng sổ: dòng booking người giữ booking phải sửa (KIEM-BOOKING-01, lọc nhiễu 24/11/2026).
    { key: 'fix', name: 'Booking thiếu ngày', money: false, booking: true,
      about: 'Chuyến có số container mà ô ngày trong booking trống hoặc sai, nên không so được với sổ. Người giữ booking sửa ở tab nguồn; lượt sau tự cập nhật.' },
  ];
  // Khi đã so với sổ web: hai nhóm thay cho 'recent'.
  const SPLIT = {
    recent: { key: 'recent', name: 'Tháng này, web chưa có', money: false, about: 'Chuyến tháng này có trong booking mà cả Sheet lẫn sổ web chưa có. Lý do máy chưa đưa vào: Báo cáo tháng.' },
    recent_web: { key: 'recent_web', name: 'Web có, Sheet chưa ghi', money: false, about: 'Máy đã đưa chuyến vào sổ web. Giá nhập ở Sổ khách trên web; từ 01/12/2026 không chờ Sheet ghi giá (WEB-CHINH-01).' },
  };
  const HEAD = '<th>Container</th><th>Ngày trên sổ</th><th>Sổ</th><th>Số tiền</th><th>Booking</th><th>Vì sao</th>';
  const FIX_HEAD = '<th>Container</th><th>Ô ngày trong booking</th><th>Tab nguồn</th><th>Booking / số xe</th><th>Chủ hàng</th><th>Việc</th>';
  const ERRORS = {
    SEA_MISSING: 'chưa có bản chụp CONT_NGUON', SEA_STALE: 'bản chụp CONT_NGUON cũ quá 3 giờ', SEA_EMPTY: 'bản chụp CONT_NGUON rỗng', SEA_UNREADABLE: 'bản chụp CONT_NGUON đọc không được',
    ROAD_MISSING: 'chưa có bản chụp CONT_BO', ROAD_STALE: 'bản chụp CONT_BO cũ quá 3 giờ', ROAD_EMPTY: 'bản chụp CONT_BO rỗng', ROAD_UNREADABLE: 'bản chụp CONT_BO đọc không được',
    SOURCE_EMPTY: 'hai bản chụp booking không có chuyến nào', SHEET_EMPTY: 'bản tải Sheet sổ nợ không có dòng chuyến', TIMEOUT: 'chạy quá 15 phút',
    WEB_EMPTY: 'đọc sổ web không thấy dòng chuyến nào',
  };
  // Phía sổ web: sổ được so là sổ web, nên tên nhóm nói "web" thay cho "sổ".
  const WEB_NAMES = {
    missing: { name: 'Booking có, web chưa có', about: 'Chuyến đã đi theo booking mà chưa sổ web nào có.' },
    nosource: { name: 'Trên web, booking không có', about: 'Sổ web tính tiền một container mà booking không có.' },
    nodate: { name: 'Web thiếu ngày', about: 'Dòng sổ web không có ngày, booking có. Không đổi tiền.' },
    recent: { name: 'Tháng này, web chưa có', about: 'Chuyến tháng này có trong booking mà sổ web chưa có. Lý do máy chưa đưa vào: Báo cáo tháng.' },
  };
  const state = { body: null, data: null, side: 'web', failed: false, open: null, book: '', ids: new Map() };
  const hasWeb = () => Boolean(state.body && typeof state.body.web_check === 'object' && state.body.web_check);
  const onWeb = () => state.side === 'web' && hasWeb();
  const pick = () => { state.data = state.body ? (onWeb() ? state.body.web_check : state.body) : null; };

  const day = iso => F.dateText(String(iso ?? '').slice(0, 10));
  const hhmm = iso => String(iso ?? '').slice(11, 16);
  const money = text => (text === null || text === undefined || text === '' ? '—' : `${String(text).replace(/\B(?=(\d{3})+(?!\d))/g, '.')}đ`);
  const count = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const monthText = key => (key ? `${Number(key.slice(5, 7))}/${key.slice(0, 4)}` : '');
  const nameKey = name => String(name ?? '').trim().split(/\s+/).join(' ');
  const split = () => !onWeb() && state.data?.recent_web === 'checked';
  const groupOf = row => (row.group === 'recent' && row.web && split() ? 'recent_web' : row.group);
  // Kết quả của lượt trước khi có `booking_fix` thì không hiện nhóm đó: hiện "0" sẽ thành "không có dòng lỗi" dù chưa kiểm.
  // Phía sổ web: thiếu chuyến là tiêu chí số 1 nên đứng đầu hàng đụng tiền.
  const ordered = () => (onWeb() ? [...GROUPS].sort((a, b) => (b.key === 'missing') - (a.key === 'missing')) : GROUPS);
  const groups = () => ordered().filter(group => !group.booking || Array.isArray(state.data?.booking_fix))
    .flatMap(group => (split() && group.key === 'recent' ? [SPLIT.recent, SPLIT.recent_web]
      : [onWeb() && WEB_NAMES[group.key] ? { ...group, ...WEB_NAMES[group.key] } : group]));
  // Dòng booking cần sửa (`booking_fix`) có hình khác dòng sổ: cột riêng, lọc theo tab nguồn thay vì theo sổ.
  const countOf = group => (group.booking ? (state.data?.booking_fix ?? []).length
    : split() && group.key in SPLIT ? state.data.rows.filter(row => groupOf(row) === group.key).length : state.data.counts?.[group.key] ?? 0);
  const groupRows = group => (group.booking ? (state.data.booking_fix ?? []) : state.data.rows.filter(row => groupOf(row) === group.key));
  const bookOf = row => row.web?.name ?? row.tab ?? row.suggest?.tab;
  const reportHref = month => `/bao-cao-thang.html?month=${encodeURIComponent(month ?? '')}&amp;webchua=1`;
  const when = iso => {
    const today = String(state.data?.now ?? '').slice(0, 10);
    return `${hhmm(iso)} ${String(iso).slice(0, 10) === today ? 'hôm nay' : `ngày ${Number(String(iso).slice(8, 10))}/${Number(String(iso).slice(5, 7))}`}`;
  };

  // Tên sổ là tên tab khách trên Sheet; sổ web cùng tên (như lượt đối soát ghép) thì có link mở sổ đúng tháng.
  function bookCell(tab, month, extra = '', id = state.ids.get(nameKey(tab))) {
    if (!tab) return '—';
    const name = id ? `<a href="/so-khach-v7-live.html?customer=${encodeURIComponent(id)}&amp;month=${esc(month ?? '')}">${esc(tab)}</a>` : esc(tab);
    return `${name}${extra}`;
  }

  function why(row) {
    const src = row.source ?? {}, pair = row.pair ?? {};
    switch (row.code) {
      case 'TRUNG': {
        const near = row.near_trips, base = 'Cùng container, cùng ngày với dòng khác có tiền';
        if (near === null || near === undefined) return base;
        return `${base}; ${near === 0 ? 'booking không có chuyến nào quanh ngày này' : near === 1 ? 'booking chỉ có 1 chuyến' : `booking có ${near} chuyến, có thể đúng là ${near} chuyến`}`;
      }
      case 'TRUNG_GAN': return `Chuyến booking ${day(src.date)} đã tính ở ${pair.tab} dòng ${pair.row}`;
      case 'TRUNG_DAO_NGAY': return `Đảo ngày/tháng thì trùng chuyến booking ${day(src.date)}, đã tính ở ${pair.tab} dòng ${pair.row}`;
      case 'CHUA_TINH': case 'CHU_HANG_CHUA_GHEP': {
        const base = row.code === 'CHUA_TINH' ? 'Chưa thấy ở sổ nào' : 'Chủ hàng chưa ứng với sổ nào';
        const near = row.near;
        // Sổ đã có dòng của container gần đó: booking nhiều chuyến hơn sổ, người xem sót một chuyến hay booking ghi lặp.
        if (!near || !near.sheet) return near ? `${base}; sổ không có dòng nào của container này trong 45 ngày quanh đó` : base;
        return `${base}; booking có ${near.booking} chuyến container này trong 45 ngày quanh đó, sổ có ${near.sheet} dòng: sót một chuyến, hay booking ghi lặp?`;
      }
      case 'KHAC_KHACH': return 'Chủ hàng trên booking khác khách của sổ';
      case 'KHONG_NGUON': return 'Không thấy container trong booking';
      case 'LECH_NGAY': return row.paired ? `Lệch ${row.gap_days} ngày` : `Chuyến booking gần nhất cách ${row.gap_days} ngày, chưa ghép`;
      case 'NGAY_TU_NGUON': return src.date && row.month && String(src.date).slice(0, 7) !== row.month ? 'Sổ không ghi ngày, ghi ở khối tháng sau' : 'Sổ không ghi ngày';
      case 'THANG_CUOI':
        if (row.web) return `Đã vào sổ web ngày ${day(row.web.date)}; giá nhập ở Sổ khách`;
        return split() || onWeb() ? 'Web chưa có' : 'Tháng này, sổ có thể chưa ghi';
      default: return '';
    }
  }

  function rowHtml(row) {
    const src = row.source;
    const sheetDay = row.date ? esc(day(row.date)) : row.raw_date ? esc(row.raw_date) : '—';
    const book = row.web ? bookCell(row.web.name ?? `sổ ${row.web.customer_id}`, row.web.date.slice(0, 7), '', row.web.customer_id)
      : row.tab && row.customer_id ? bookCell(row.tab, row.month, '', row.customer_id)   // phía sổ web: mã sổ có sẵn
      : row.tab ? bookCell(row.tab, row.month, ` <span class="bk-sub">dòng ${esc(row.row)}</span>`)
      : row.suggest ? `<span class="bk-sub">gợi ý</span> ${bookCell(row.suggest.tab, row.month)}` : '—';
    // Web chưa có: lý do máy giữ từng chuyến nằm ở danh sách "web chưa có" của Báo cáo tháng (BAO-CAO-THANG-02).
    const reason = groupOf(row) === 'recent' && (split() || onWeb()) && src?.date
      ? `${esc(why(row))}: <a href="${reportHref(src.date.slice(0, 7))}">xem lý do</a>` : esc(why(row));
    // Chỉ dòng "booking không có" mới ghi "không có"; dòng chưa ghép của cặp tính hai lần thì chuyến đã ghép dòng kia, để trống.
    const booking = src ? `${esc(day(src.date))} · ${src.kind === 'BO' ? 'Bộ' : 'Biển'}${src.owner ? `<span class="bk-sub bk-line">${esc(src.owner)}</span>` : ''}`
      : row.code === 'KHONG_NGUON' ? '<span class="bk-sub">không có</span>' : '—';
    return `<tr><td class="bk-cont">${esc(row.container)}</td><td class="num">${sheetDay}</td><td>${book}</td><td class="num">${esc(money(row.amount_vnd))}</td><td>${booking}</td><td>${reason}</td></tr>`;
  }

  function statusLine(data) {
    if (state.failed && !data) return ['bad', 'Không tải được kết quả kiểm booking. Bấm Làm mới để thử lại.'];
    if (!data) return ['', 'Đang tải…'];
    const error = data.last_error, reason = error ? (ERRORS[error.reason] ?? `mã ${error.reason}`) : '';
    if (data.state === 'none') return error ? ['bad', `Lượt kiểm ${when(error.at)} lỗi: ${reason}. Chưa có kết quả nào.`] : ['warn', 'Chưa có lượt kiểm nào. Kết quả có sau lượt đối soát kế tiếp (phút 05 mỗi giờ, 7–22 giờ).'];
    const sheet = data.sheet ?? {}, booking = data.booking ?? {};
    const base = onWeb() ? `${count(booking.on_web ?? 0)}/${count(booking.trips ?? 0)} chuyến booking đã có trên sổ web`
      : `${count(sheet.paired ?? 0)}/${count(sheet.rows ?? 0)} dòng chuyến khớp booking`;
    if (data.state === 'error') return ['bad', `Lượt kiểm ${when(error.at)} lỗi: ${reason}. Số dưới đây của lượt ${when(data.checked_at)}, có thể cũ.`];
    if (data.state === 'stale') return ['warn', `Lượt kiểm gần nhất ${when(data.checked_at)}, đã lỡ các lượt sau. Số dưới đây có thể cũ.`];
    const clean = GROUPS.filter(group => group.money).every(group => !countOf(group));
    return [clean ? 'ok' : '', `Lượt ${when(data.checked_at)} · ${base}${clean ? '. Không thấy chuyến nào nghi tính hai lần, sót, sai khách hay thiếu booking.' : ''}`];
  }

  function sides() {
    const box = $('bk-sides');
    box.hidden = !hasWeb();
    for (const button of box.querySelectorAll('button[data-side]')) button.setAttribute('aria-pressed', String(button.dataset.side === (onWeb() ? 'web' : 'sheet')));
  }

  function render() {
    pick();
    sides();
    const data = state.data, hasRows = Array.isArray(data?.rows) && data.state !== 'none';
    const [tone, line] = statusLine(data);
    const status = $('bk-status');
    status.className = `bk-status ${tone}`;
    status.textContent = line;
    const scope = data?.window;
    const range = scope ? `Kiểm chuyến biển từ ${monthText(scope.BIEN)}, chuyến bộ từ ${monthText(scope.BO)} tới nay, theo hai bản chụp CONT_NGUON và CONT_BO.` : '';
    $('bk-scope').textContent = !scope ? '' : onWeb()
      ? `${range} Web đủ chuyến booking là tiêu chí số 1. Chuyến trước tháng đầu của sổ nằm trong số dư đầu kỳ nên không tính. Chỉ so, không ghi.`
      : `${range} Chỉ so; sửa trên Sheet thì lượt sau tự cập nhật.`;
    $('bk-groups').hidden = !hasRows;
    if (!hasRows) { $('bk-list').hidden = true; return; }
    const button = group => {
      const n = countOf(group);
      return `<button type="button" class="bk-group${group.money ? ' money' : ''}${n ? ' has' : ''}" data-group="${group.key}" aria-expanded="${state.open === group.key}"${n ? '' : ' disabled'}><span>${esc(group.name)}</span><b>${count(n)}</b></button>`;
    };
    $('bk-groups').innerHTML = `<div class="bk-row">${groups().filter(g => g.money).map(button).join('')}</div><div class="bk-row bk-info"><span class="bk-sub">Không đổi tiền:</span>${groups().filter(g => !g.money).map(button).join('')}</div>`;
    renderList();
  }

  function fixHtml(row) {
    const raw = String(row.raw_date ?? '').trim();
    const owner = row.owner ? `<span class="bk-sub bk-line">${esc(row.owner)}</span>` : '';
    return `<tr><td class="bk-cont">${esc(row.cont)}</td><td class="num">${raw ? esc(raw) : '<span class="bk-sub">trống</span>'}</td>`
      + `<td>${esc(row.tab)} <span class="bk-sub">dòng ${esc(row.line ?? '—')}</span></td><td>${esc(row.ref || '—')}</td>`
      + `<td>${row.family === 'BO' ? 'Bộ' : 'Biển'}${owner}</td><td>Ghi ngày vào ô ngày ở tab nguồn</td></tr>`;
  }

  function renderList() {
    const list = $('bk-list'), group = groups().find(item => item.key === state.open);
    const rows = group ? groupRows(group) : [];
    list.hidden = !rows.length;
    if (!rows.length) return;
    const keyOf = row => (group.booking ? row.tab : bookOf(row));
    const books = [...new Set(rows.map(keyOf).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
    if (state.book && !books.includes(state.book)) state.book = '';
    const shown = state.book ? rows.filter(row => keyOf(row) === state.book) : rows;
    $('bk-list-name').textContent = `${group.name} · ${count(shown.length)}${state.book ? ` / ${count(rows.length)}` : ''}`;
    $('bk-list-about').textContent = group.about;
    $('bk-filter-name').textContent = group.booking ? 'Tab nguồn' : 'Sổ';
    $('bk-book').innerHTML = `<option value="">${group.booking ? 'Mọi tab' : 'Mọi sổ'} (${books.length})</option>${books.map(book => `<option value="${esc(book)}"${book === state.book ? ' selected' : ''}>${esc(book)}</option>`).join('')}`;
    list.classList.toggle('fix', Boolean(group.booking));
    $('bk-headrow').innerHTML = group.booking ? FIX_HEAD : HEAD;
    $('bk-body').innerHTML = shown.map(group.booking ? fixHtml : rowHtml).join('');
  }

  async function loadIds() {
    try {
      const body = await CongNoNet.customers();
      const seen = new Map();
      for (const row of body.customers ?? []) { const key = nameKey(row.name); seen.set(key, seen.has(key) ? null : row.id); }   // hai sổ cùng tên thì không đoán
      state.ids = new Map([...seen].filter(([, id]) => id !== null));
    } catch { /* không có link mở sổ thì vẫn đọc được */ }
  }

  let timer = null;
  async function load() {
    clearTimeout(timer);
    try {
      const response = await fetch('/api/v7/machine/booking', { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT) });
      if (!response.ok) throw new Error(String(response.status));
      state.body = await response.json();
      state.failed = false;
    } catch {
      state.failed = true;
      state.body = null;   // không giữ số cũ khi không biết nó còn đúng không
    }
    render();
    timer = setTimeout(load, REFRESH);
  }

  $('bk-groups').addEventListener('click', event => {
    const button = event.target.closest('button[data-group]');
    if (!button) return;
    state.open = state.open === button.dataset.group ? null : button.dataset.group;
    state.book = '';
    render();
  });
  $('bk-sides').addEventListener('click', event => {
    const button = event.target.closest('button[data-side]');
    if (!button || button.dataset.side === state.side) return;
    state.side = button.dataset.side;
    state.open = null;
    state.book = '';
    render();
  });
  $('bk-book').addEventListener('change', event => { state.book = event.target.value; renderList(); });
  $('refresh-data').addEventListener('click', () => load());
  Promise.all([loadIds(), load()]).then(render);
})();
