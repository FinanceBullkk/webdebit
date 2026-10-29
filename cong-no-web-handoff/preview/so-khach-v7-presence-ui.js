/* Sổ khách: ô người khác đang chọn/đang sửa và câu báo sổ vừa đổi kèm tên (PRESENCE-01 mức 1). */
(() => {
  'use strict';
  window.SoKhachV7LiveParts = window.SoKhachV7LiveParts || {};
  window.SoKhachV7LiveParts.presence = ctx => {
    const { root, customerId, live } = ctx;
    if (!window.Presence) return;

    // Vị trí của mình: khóa dòng (trip:11, legacy:21, draft:<tháng>) + cột theo thứ tự ô, không theo tọa độ màn hình.
    function position() {
      const active = document.activeElement;
      if (!active || !root.contains(active)) return { month: null, cell: null };
      const month = active.closest('section[id^="thang-"]')?.id.match(/^thang-(\d{4}-\d{2})/)?.[1] ?? null;
      const td = active.closest('td');
      if (!td) return { month, cell: null };
      const col = `c${td.cellIndex}`;
      if (active.matches('.draft-input')) return { month, cell: { row: `draft:${active.dataset.month}`, col, editing: true } };
      const key = td.closest('tr[data-row]')?.dataset.row.match(/^([a-z]+)-([0-9]+)$/);
      if (!key) return { month, cell: null };
      return { month, cell: { row: `${key[1]}:${key[2]}`, col, editing: active !== td && active.matches('input,textarea,select') } };
    }

    function target(cell) {
      if (cell.row.startsWith('draft:')) {
        const input = root.querySelector(`.draft-input[data-month="${CSS.escape(cell.row.slice(6))}"]`);
        return input?.closest('tr') ?? null;
      }
      const [kind, id] = cell.row.split(':');
      const row = root.querySelector(`tr[data-row="${CSS.escape(`${kind}-${id}`)}"]`);
      return row?.cells[Number(cell.col.slice(1))] ?? null;
    }

    function decorate(people, colors) {
      for (const node of root.querySelectorAll('.presence-cell,.presence-row,[data-presence]')) {
        node.classList.remove('presence-cell', 'presence-row', 'editing');
        node.removeAttribute('data-presence');
        node.style.removeProperty('--pc');
      }
      for (const person of people) {
        const node = person.cell && target(person.cell);
        if (!node || node.dataset.presence) continue;
        const draft = person.cell.row.startsWith('draft:');
        const label = draft ? `${person.name} đang nhập chuyến…` : person.cell.editing ? `${person.name} đang sửa…` : person.name;
        const mark = draft ? node.cells[0] : node;
        node.classList.add(draft ? 'presence-row' : 'presence-cell');
        if (person.cell.editing && !draft) node.classList.add('editing');
        node.dataset.presence = label;
        mark.dataset.presence = label;
        node.style.setProperty('--pc', colors[person.color % colors.length]);
      }
    }

    function onJump(person) {
      const node = person.cell && target(person.cell);
      if (!node) return;
      node.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      node.classList.add('presence-flash');
      setTimeout(() => node.classList.remove('presence-flash'), 1000);
    }

    const presence = window.Presence.start({ page: 'so-khach', customerId, position, decorate, onJump });
    // Câu báo sổ vừa đổi kèm tên người cùng mở sổ, để biết ai vừa sửa (chống ghi đè vẫn do phiên bản sổ).
    ctx.presenceStale = message => {
      const others = presence?.people().filter(presence.sameBook).map(person => person.name) ?? [];
      if (message !== live.stale || !others.length) return message;
      return message.replace('Sổ vừa thay đổi.', `Sổ vừa thay đổi (${[...new Set(others)].join(', ')} cũng đang mở sổ này).`);
    };
  };
})();
