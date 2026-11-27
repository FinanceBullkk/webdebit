/* Tìm chuyến theo số cont trong ô Tìm khách (TIM-CONT-01, 28/11/2026). Dùng chung cho menu trái (app-nav.js) và hộp đổi khách
 * của Sổ khách (so-khach-v7-api.js): gõ chuỗi có chữ số, 4–20 ký tự sau khi bỏ khoảng trắng, thì sau 250 ms ngừng gõ hỏi
 * GET /api/v7/containers/find (chuyến web và dòng chuyến sổ gốc của mọi sổ, khớp một phần). Mỗi kết quả mở Sổ khách đúng tháng
 * nợ, tô dòng có số cont đó (?cont=, so-khach-v7-loc-ui.js). Chỉ đọc; không lưu gì trên máy. */
globalThis.TimCont = (() => {
  'use strict';
  const F = CongNoFormat;
  const squash = raw => String(raw ?? '').replace(/\s/g, '');
  // Tên khách hiếm khi có chữ số, số cont luôn có: chỉ chuỗi có số mới hỏi máy chủ, gõ tên thì không tốn lượt gọi.
  const wants = raw => { const key = squash(raw); return key.length >= 4 && key.length <= 20 && /\d/.test(key); };
  const href = item => `/so-khach-v7-live.html?customer=${encodeURIComponent(item.customer_id)}`
    + `&month=${encodeURIComponent(String(item.debt_month ?? '').slice(0, 7))}&cont=${encodeURIComponent(squash(item.container))}`;
  const when = item => (item.date ? F.dateText(item.date) : `T${F.monthLabel(item.debt_month)}`);
  const NOTE = { pending: 'chờ kiểm', legacy: 'sổ gốc' };

  // Hỏi máy chủ cho chuỗi đang gõ; onState nhận { query, loading } rồi { query, body } hoặc { query, error }; chuỗi không giống
  // số cont thì nhận null ngay. Lượt cũ về muộn hơn lượt mới thì bỏ.
  function searcher(onState) {
    let turn = 0, timer = null;
    return raw => {
      clearTimeout(timer);
      const mine = ++turn;
      const query = String(raw ?? '').trim();
      if (!wants(query)) { onState(null); return; }
      onState({ query, loading: true });
      timer = setTimeout(async () => {
        try {
          const body = await CongNoNet.fetchJson(`/api/v7/containers/find?q=${encodeURIComponent(query)}`, { what: 'kết quả tìm số cont' });
          if (mine === turn) onState({ query, body });
        } catch (error) {
          if (mine === turn) onState({ query, error: CongNoNet.messageOf(error, 'Không tìm được số cont.') });
        }
      }, 250);
    };
  }

  // Khối "Số cont" của danh sách: tiêu đề rồi mỗi chuyến một link "SỐ CONT · khách · ngày"; names: Map id → tên sổ.
  function html(state, names, headClass) {
    if (!state) return '';
    const head = text => `<div class="${headClass}" role="presentation">${F.esc(text)}</div>`;
    if (state.loading) return head('Số cont · đang tìm…');
    if (state.error) return head(state.error);
    const items = state.body?.items ?? [];
    if (!items.length) return head(`Không có chuyến nào có số cont “${state.query}”`);
    const rows = items.map(item => {
      const name = names.get(String(item.customer_id)) ?? `Sổ ${item.customer_id}`;
      const route = [item.origin, item.destination].filter(Boolean).join(' → ');
      const note = NOTE[item.source] ? ` · ${NOTE[item.source]}` : '';
      return `<a role="option" class="cont-hit" href="${F.esc(href(item))}"${route ? ` title="${F.esc(route)}"` : ''}>`
        + `<b>${F.esc(item.container)}</b> · ${F.esc(name)} · ${F.esc(when(item))}${F.esc(note)}</a>`;
    });
    return head(`Số cont (${items.length}${state.body.more ? '+' : ''})`) + rows.join('')
      + (state.body.more ? head('Còn nữa · gõ thêm số để lọc') : '');
  }

  return { wants, href, searcher, html };
})();
