/* Sổ khách V7 bản live — mở từ "Việc cần làm" ở Tổng quan: ?loc=thieu-gia|cho-kiem tô các chuyến cần xử lý và có nút
 * nhảy tới từng dòng. Không ẩn dòng nào, để số cộng trong tháng vẫn đọc đúng như sổ. Tách từ so-khach-v7-ui.js
 * (31/10/2026, DOM không đổi). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).loc = ctx => {
  'use strict';
  const { root } = ctx;
  const LOC = {
    'thieu-gia': ['chuyến thiếu đơn giá', trip => trip.status === 'confirmed' && trip.is_missing_price === true],
    'cho-kiem': ['chuyến chờ kiểm', trip => trip.status === 'pending_review'],
  };
  let locKind = new URLSearchParams(location.search).get('loc');
  let locJumped = false;
  let locIndex = 0;
  // Gọi sau mỗi lần vẽ sổ: tô lại các dòng và dựng lại thanh trên bảng tháng.
  function locAfterRender(data) {
    const rule = Object.hasOwn(LOC, locKind ?? '') ? LOC[locKind] : null;
    if (!rule) return;
    const hits = (data.trips ?? []).filter(trip => !trip.deleted && rule[1](trip))
      .map(trip => root.querySelector(`[data-row="trip-${trip.id}"]`)).filter(Boolean);
    hits.forEach(row => row.classList.add('loc-hit'));
    const bar = document.createElement('div');
    bar.className = 'loc-bar';
    bar.setAttribute('role', 'status');
    bar.innerHTML = hits.length
      ? `<span><b>${hits.length} ${rule[0]}</b> được tô vàng trong sổ.</span><button type="button" class="loc-next">Đến dòng tiếp ›</button>`
        + '<button type="button" class="loc-clear">Bỏ đánh dấu</button>'
      : `<span>Sổ này không còn ${rule[0]}.</span><a href="/dashboard-v7.html">Về Tổng quan</a><button type="button" class="loc-clear">Đóng</button>`;
    root.querySelector('.layout')?.before(bar);
    // Sổ có thể vẽ lại (tự cập nhật) giữa hai lần bấm: luôn đọc dòng đang có trên màn hình.
    const go = index => {
      const rows = [...root.querySelectorAll('tr.loc-hit')];
      if (!rows.length) return;
      locIndex = index % rows.length;
      rows[locIndex].scrollIntoView({ block: 'center' });
    };
    bar.querySelector('.loc-next')?.addEventListener('click', () => go(locIndex + 1));
    bar.querySelector('.loc-clear').addEventListener('click', () => {
      locKind = null;
      const query = new URLSearchParams(location.search); query.delete('loc');
      window.history.replaceState(null, '', `${location.pathname}?${query}`);
      root.querySelectorAll('tr.loc-hit').forEach(row => row.classList.remove('loc-hit'));
      root.querySelectorAll('.loc-bar').forEach(node => node.remove());
    });
    if (!locJumped && hits.length) { locJumped = true; go(0); }
  }
  Object.assign(ctx, { locAfterRender });
};
