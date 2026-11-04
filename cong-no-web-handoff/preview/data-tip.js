/* Ô chú thích khi rê chuột hoặc focus bàn phím, dùng chung cho Tổng quan và Bảng thu (gom từ dashboard-v7.js 4/11/2026): phần tử có
   data-tip nằm trong `scope`, dòng đầu đậm, các dòng sau là chi tiết. Trang đặt sẵn <div class="tip" id="tip" role="tooltip" hidden></div>. */
globalThis.DataTip = (() => {
  'use strict';
  function mount(scope) {
    const tip = document.getElementById('tip');
    const hide = () => { tip.hidden = true; };
    function show(el) {
      if (el.disabled || !el.dataset.tip) return hide();
      tip.replaceChildren(...el.dataset.tip.split('\n').map((line, index) => {
        const node = document.createElement(index === 0 ? 'b' : 'span');
        node.textContent = line;
        return node;
      }));
      tip.hidden = false;
      const box = el.getBoundingClientRect();
      const left = Math.min(Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2), innerWidth - tip.offsetWidth - 8);
      const above = box.top - tip.offsetHeight - 8;
      tip.style.left = `${left}px`;
      tip.style.top = `${above > 8 ? above : box.bottom + 8}px`;
    }
    const tipOf = target => target.closest?.(`${scope} [data-tip]`);
    document.addEventListener('pointerover', event => { const el = tipOf(event.target); if (el) show(el); else hide(); });
    document.addEventListener('focusin', event => { const el = tipOf(event.target); if (el) show(el); else hide(); });
    document.addEventListener('focusout', hide);
    addEventListener('scroll', hide, { passive: true });
  }
  return { mount };
})();
