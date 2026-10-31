/* Sổ khách: ô người khác đang chọn/đang sửa, câu báo sổ vừa đổi kèm tên (PRESENCE-01 mức 1), mũi tên chuột (mức 2). */
(() => {
  'use strict';
  window.SoKhachV7LiveParts = window.SoKhachV7LiveParts || {};
  window.SoKhachV7LiveParts.presence = ctx => {
    const { root, customerId, live } = ctx;
    if (!window.Presence) return;

    // Vị trí của mình: khóa dòng (trip:11, legacy:21) + cột theo thứ tự ô, không theo tọa độ màn hình.
    function position() {
      const active = document.activeElement;
      if (!active || !root.contains(active)) return { month: null, cell: null };
      const month = active.closest('section[id^="thang-"]')?.id.match(/^thang-(\d{4}-\d{2})/)?.[1] ?? null;
      const td = active.closest('td');
      if (!td) return { month, cell: null };
      const col = `c${td.cellIndex}`;
      const row = rowKey(td);
      if (!row) return { month, cell: null };
      return { month, cell: { row, col, editing: active !== td && active.matches('input,textarea,select') } };
    }

    // Khóa dòng ổn định từ data-row (trip-11 → trip:11); hàng nháp, dòng cộng, phiếu rời không có khóa.
    function rowKey(td) {
      const key = td.closest('tr[data-row]')?.dataset.row.match(/^([a-z]+)-([0-9]+)$/);
      return key ? `${key[1]}:${key[2]}` : null;
    }

    // Mức 2: chuột của mình trên bảng sổ, quy về ô + phần nghìn trong ô.
    let mouse = null;
    const permille = (value, size) => Math.max(0, Math.min(1000, Math.round(value / size * 1000)));
    root.addEventListener('mousemove', event => {
      const td = event.target.closest?.('td');
      const row = td && root.contains(td) && rowKey(td);
      if (!row) {
        if (mouse) { mouse = null; presence?.move(); }
        return;
      }
      const box = td.getBoundingClientRect();
      mouse = { row, col: `c${td.cellIndex}`, fx: permille(event.clientX - box.left, box.width), fy: permille(event.clientY - box.top, box.height) };
      presence?.move();
    });
    root.addEventListener('mouseleave', () => { if (mouse) { mouse = null; presence?.move(); } });

    function target(cell) {
      const [kind, id] = cell.row.split(':');
      const row = root.querySelector(`tr[data-row="${CSS.escape(`${kind}-${id}`)}"]`);
      return row?.cells[Number(cell.col.slice(1))] ?? null;
    }

    function decorate(people, colors) {
      for (const node of root.querySelectorAll('.presence-cell,[data-presence]')) {
        node.classList.remove('presence-cell', 'editing');
        node.removeAttribute('data-presence');
        node.style.removeProperty('--pc');
      }
      for (const person of people) {
        const node = person.cell && target(person.cell);
        if (!node || node.dataset.presence) continue;
        const label = person.cell.editing ? `${person.name} đang sửa…` : person.name;
        node.classList.add('presence-cell');
        if (person.cell.editing) node.classList.add('editing');
        node.dataset.presence = label;
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

    // Nút Ẩn/Hiện con trỏ ở cạnh "Làm mới" (dải dưới đầu sổ), không ở thanh xanh trên cùng (SO-GON-04, L7).
    const presence = window.Presence.start({ page: 'so-khach', customerId, position, decorate, onJump, pointer: () => mouse, locate: target,
      toggleHost: document.querySelector('#live-controls') ?? undefined });
    // Câu báo sổ vừa đổi kèm tên người cùng mở sổ, để biết ai vừa sửa (chống ghi đè vẫn do phiên bản sổ).
    ctx.presenceStale = message => {
      const others = presence?.people().filter(presence.sameBook).map(person => person.name) ?? [];
      if (message !== live.stale || !others.length) return message;
      return message.replace('Sổ vừa thay đổi.', `Sổ vừa thay đổi (${[...new Set(others)].join(', ')} cũng đang mở sổ này).`);
    };
  };
})();
