/* Khối "Kiểm Sheet sổ nợ với booking" của tab Máy chạy (KIEM-BOOKING-01). Chỉ xem: đọc /api/v7/machine/booking, không có lệnh ghi.
 * Thứ tự theo câu chủ sổ hỏi: lượt kiểm gần nhất có tin được không, rồi bốn nhóm đụng tiền, rồi ba nhóm chỉ để biết. Bấm nhóm thì mở
 * danh sách ngay dưới. Chưa có kết quả, kết quả cũ hay lượt lỗi thì nói rõ, không bao giờ hiện như "không có gì lệch". */
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
  ];
  const ERRORS = {
    SEA_MISSING: 'chưa có bản chụp CONT_NGUON', SEA_STALE: 'bản chụp CONT_NGUON cũ quá 3 giờ', SEA_EMPTY: 'bản chụp CONT_NGUON rỗng', SEA_UNREADABLE: 'bản chụp CONT_NGUON đọc không được',
    ROAD_MISSING: 'chưa có bản chụp CONT_BO', ROAD_STALE: 'bản chụp CONT_BO cũ quá 3 giờ', ROAD_EMPTY: 'bản chụp CONT_BO rỗng', ROAD_UNREADABLE: 'bản chụp CONT_BO đọc không được',
    SOURCE_EMPTY: 'hai bản chụp booking không có chuyến nào', SHEET_EMPTY: 'bản tải Sheet sổ nợ không có dòng chuyến', TIMEOUT: 'chạy quá 15 phút',
  };
  const state = { data: null, failed: false, open: null, book: '', ids: new Map() };

  const day = iso => F.dateText(String(iso ?? '').slice(0, 10));
  const hhmm = iso => String(iso ?? '').slice(11, 16);
  const money = text => (text === null || text === undefined || text === '' ? '—' : `${String(text).replace(/\B(?=(\d{3})+(?!\d))/g, '.')}đ`);
  const count = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const monthText = key => (key ? `${Number(key.slice(5, 7))}/${key.slice(0, 4)}` : '');
  const nameKey = name => String(name ?? '').trim().split(/\s+/).join(' ');
  const when = iso => {
    const today = String(state.data?.now ?? '').slice(0, 10);
    return `${hhmm(iso)} ${String(iso).slice(0, 10) === today ? 'hôm nay' : `ngày ${Number(String(iso).slice(8, 10))}/${Number(String(iso).slice(5, 7))}`}`;
  };

  // Tên sổ là tên tab khách trên Sheet; sổ web cùng tên (như lượt đối soát ghép) thì có link mở sổ đúng tháng.
  function bookCell(tab, month, extra = '') {
    if (!tab) return '—';
    const id = state.ids.get(nameKey(tab));
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
      case 'CHUA_TINH': return 'Chưa thấy ở sổ nào';
      case 'CHU_HANG_CHUA_GHEP': return 'Chủ hàng chưa ứng với sổ nào';
      case 'KHAC_KHACH': return 'Chủ hàng trên booking khác khách của sổ';
      case 'KHONG_NGUON': return 'Không thấy container trong booking';
      case 'LECH_NGAY': return row.paired ? `Lệch ${row.gap_days} ngày` : `Chuyến booking gần nhất cách ${row.gap_days} ngày, chưa ghép`;
      case 'NGAY_TU_NGUON': return 'Sổ không ghi ngày';
      case 'THANG_CUOI': return 'Tháng này, sổ có thể chưa ghi';
      default: return '';
    }
  }

  function rowHtml(row) {
    const src = row.source;
    const sheetDay = row.date ? esc(day(row.date)) : row.raw_date ? esc(row.raw_date) : '—';
    const book = row.tab ? bookCell(row.tab, row.month, ` <span class="bk-sub">dòng ${esc(row.row)}</span>`)
      : row.suggest ? `<span class="bk-sub">gợi ý</span> ${bookCell(row.suggest.tab, row.month)}` : '—';
    // Chỉ dòng "booking không có" mới ghi "không có"; dòng chưa ghép của cặp tính hai lần thì chuyến đã ghép dòng kia, để trống.
    const booking = src ? `${esc(day(src.date))} · ${src.kind === 'BO' ? 'Bộ' : 'Biển'}${src.owner ? `<span class="bk-sub bk-line">${esc(src.owner)}</span>` : ''}`
      : row.code === 'KHONG_NGUON' ? '<span class="bk-sub">không có</span>' : '—';
    return `<tr><td class="bk-cont">${esc(row.container)}</td><td class="num">${sheetDay}</td><td>${book}</td><td class="num">${esc(money(row.amount_vnd))}</td><td>${booking}</td><td>${esc(why(row))}</td></tr>`;
  }

  function statusLine(data) {
    if (state.failed && !data) return ['bad', 'Không tải được kết quả kiểm booking. Bấm Làm mới để thử lại.'];
    if (!data) return ['', 'Đang tải…'];
    const error = data.last_error, reason = error ? (ERRORS[error.reason] ?? `mã ${error.reason}`) : '';
    if (data.state === 'none') return error ? ['bad', `Lượt kiểm ${when(error.at)} lỗi: ${reason}. Chưa có kết quả nào.`] : ['warn', 'Chưa có lượt kiểm nào. Kết quả có sau lượt đối soát kế tiếp (phút 05 mỗi giờ, 7–22 giờ).'];
    const sheet = data.sheet ?? {}, base = `${count(sheet.paired ?? 0)}/${count(sheet.rows ?? 0)} dòng chuyến khớp booking`;
    if (data.state === 'error') return ['bad', `Lượt kiểm ${when(error.at)} lỗi: ${reason}. Số dưới đây của lượt ${when(data.checked_at)}, có thể cũ.`];
    if (data.state === 'stale') return ['warn', `Lượt kiểm gần nhất ${when(data.checked_at)}, đã lỡ các lượt sau. Số dưới đây có thể cũ.`];
    const clean = GROUPS.filter(group => group.money).every(group => !(data.counts?.[group.key]));
    return [clean ? 'ok' : '', `Lượt ${when(data.checked_at)} · ${base}${clean ? '. Không thấy chuyến nào nghi tính hai lần, sót, sai khách hay thiếu booking.' : ''}`];
  }

  function render() {
    const data = state.data, hasRows = Array.isArray(data?.rows) && data.state !== 'none';
    const [tone, line] = statusLine(data);
    const status = $('bk-status');
    status.className = `bk-status ${tone}`;
    status.textContent = line;
    const scope = data?.window;
    $('bk-scope').textContent = scope ? `Kiểm chuyến biển từ ${monthText(scope.BIEN)}, chuyến bộ từ ${monthText(scope.BO)} tới nay, theo hai bản chụp CONT_NGUON và CONT_BO. Chỉ so; sửa trên Sheet thì lượt sau tự cập nhật.` : '';
    $('bk-groups').hidden = !hasRows;
    if (!hasRows) { $('bk-list').hidden = true; return; }
    const button = group => {
      const n = data.counts?.[group.key] ?? 0;
      return `<button type="button" class="bk-group${group.money ? ' money' : ''}${n ? ' has' : ''}" data-group="${group.key}" aria-expanded="${state.open === group.key}"${n ? '' : ' disabled'}><span>${esc(group.name)}</span><b>${count(n)}</b></button>`;
    };
    $('bk-groups').innerHTML = `<div class="bk-row">${GROUPS.filter(g => g.money).map(button).join('')}</div><div class="bk-row bk-info"><span class="bk-sub">Không đổi tiền:</span>${GROUPS.filter(g => !g.money).map(button).join('')}</div>`;
    renderList();
  }

  function renderList() {
    const list = $('bk-list'), group = GROUPS.find(item => item.key === state.open);
    const rows = group ? state.data.rows.filter(row => row.group === group.key) : [];
    list.hidden = !rows.length;
    if (!rows.length) return;
    const books = [...new Set(rows.map(row => row.tab ?? row.suggest?.tab).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
    if (state.book && !books.includes(state.book)) state.book = '';
    const shown = state.book ? rows.filter(row => (row.tab ?? row.suggest?.tab) === state.book) : rows;
    $('bk-list-name').textContent = `${group.name} · ${count(shown.length)}${state.book ? ` / ${count(rows.length)}` : ''}`;
    $('bk-list-about').textContent = group.about;
    $('bk-book').innerHTML = `<option value="">Mọi sổ (${books.length})</option>${books.map(book => `<option value="${esc(book)}"${book === state.book ? ' selected' : ''}>${esc(book)}</option>`).join('')}`;
    $('bk-body').innerHTML = shown.map(rowHtml).join('');
  }

  async function loadIds() {
    try {
      const response = await fetch('/api/v7/customers', { cache: 'no-store' });
      if (!response.ok) return;
      const body = await response.json();
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
      state.data = await response.json();
      state.failed = false;
    } catch {
      state.failed = true;
      state.data = null;   // không giữ số cũ khi không biết nó còn đúng không
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
  $('bk-book').addEventListener('change', event => { state.book = event.target.value; renderList(); });
  $('refresh-data').addEventListener('click', () => load());
  Promise.all([loadIds(), load()]).then(render);
})();
