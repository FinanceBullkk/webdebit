/* Sổ khách V7 bản live — Lịch sử thay đổi: mỗi sự kiện một dòng "giờ · người làm · câu", ghi chú/lý do chỉ hiện khi có,
 * lọc theo loại (SO-GON-04, L6). Người làm là tên ngắn server gắn theo bảng tên của PRESENCE-01 (`actor_name`), không phải login.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).history = ctx => {
  'use strict';
  const { root, api, escape, dateText, fmt, monthKey, monthLabel, model } = ctx;
    // Câu chữ dùng chung với tab Đã làm của Việc cần làm (so-khach-v7-lich-su-cau.js, HOAT-DONG-01).
    const { labelOf, GROUPS, groupOf, describeEvent, noteOf, eventTime, actorName, reviewReasonText } = globalThis.LichSuCau.create({
      fmt, dateText, monthKey, monthLabel, model, feeTypeName: id => ctx.feeTypeName(id), snapshot: () => ctx.snapshot });
    // Khung Lịch sử (nút "Lịch sử" ở đầu sổ). Bộ lọc giữ qua các lần vẽ lại; bấm lọc chỉ đổi thuộc tính, không vẽ lại sổ.
    let filter = 'all';
    function listHtml(events) {
      if (!events.length) return '<p>Chưa có thay đổi nào</p>';
      const groups = events.map(groupOf);
      const count = key => key === 'all' ? events.length : groups.filter(group => group === key).length;
      const buttons = GROUPS.map(([key, label]) => `<button type="button" data-filter="${key}" aria-pressed="${key === filter}">${label} (${count(key)})</button>`).join('');
      const items = events.map((event, index) => {
        const text = describeEvent(event), note = noteOf(event);
        return `<li data-group="${groups[index]}"><time>${escape(eventTime(event.at))}</time> · <span class="who">${escape(actorName(event))}</span> · `
          + `<strong>${escape(labelOf(event))}</strong>${text ? ` ${escape(text)}` : ''}${note ? `<small>${escape(note)}</small>` : ''}</li>`;
      }).join('');
      return `<div class="history-filter" role="group" aria-label="Lọc Lịch sử theo loại">${buttons}</div>`
        + `<ol class="history-items" data-filter="${filter}">${items}</ol><p class="history-none"${count(filter) ? ' hidden' : ''}>Không có thay đổi loại này.</p>`;
    }
    // MO-SO-NHANH-02: thân GET sổ không có events; khung mở mới nạp, giữ theo version của bản GET đang vẽ. Sổ đổi là nạp lại,
    // đóng rồi mở lại khi sổ chưa đổi thì không gọi nữa. Nhận về thì chỉ thay thân khung, không vẽ lại cả sổ.
    let held = null;      // { version, events } đã nạp
    let asked = null;     // version đang nạp
    let failed = null;    // version nạp lỗi; chỉ thử lại khi bấm Thử lại hoặc sổ đổi
    const body = html => `<div class="history-body">${html}</div>`;
    const waiting = () => '<p class="history-wait" role="status">Đang tải lịch sử…</p>';
    const failure = () => '<div class="load-error" role="alert"><p>Không tải được lịch sử.</p><button type="button" class="history-retry">Thử lại</button></div>';
    function paint(html) {
      const area = root.querySelector('.history-body');
      if (!area) return;
      const keepFocus = area.contains(document.activeElement);
      area.innerHTML = html;
      if (keepFocus) root.querySelector('.history-close')?.focus();
    }
    function load(version) {
      if (asked === version) return;
      asked = version;
      failed = null;
      api.readEvents().then(data => {
        if (asked !== version) return;
        asked = null;
        held = { version, events: data.events };
        paint(listHtml(data.events));
      }, () => {
        if (asked !== version) return;
        asked = null;
        failed = version;
        paint(failure());
      });
    }
    function historyList(data) {
      if (Array.isArray(data.events)) return body(listHtml(data.events));   // server chưa tách Lịch sử
      if (held?.version === data.version) return body(listHtml(held.events));
      if (!ctx.historyOpen) return body('');
      if (failed === data.version) return body(failure());
      load(data.version);
      return body(waiting());
    }
    root.addEventListener('click', event => {
      if (!event.target.closest('.history-retry') || !ctx.snapshot) return;
      paint(waiting());
      load(ctx.snapshot.version);
    });
    root.addEventListener('click', event => {
      const button = event.target.closest('.history-filter button');
      if (!button) return;
      filter = button.dataset.filter;
      const panel = button.closest('.history-panel');
      panel.querySelector('.history-items').dataset.filter = filter;
      panel.querySelectorAll('.history-filter button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      panel.querySelector('.history-none').hidden = panel.querySelectorAll(filter === 'all' ? '.history-items > li' : `.history-items > li[data-group="${filter}"]`).length > 0;
    });
    Object.assign(ctx, { reviewReasonText, historyList });
};
