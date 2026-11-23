/* Hộp thoại tự viết thành hộp chặn thật: khi có phần tử [aria-modal="true"] đang hiện, phần còn lại của trang là `inert`
 * (audit giao diện 23/11/2026, F4).
 *
 * Trước đây các hộp của Sổ khách (debit note, hỏi lại phụ phí, cài đặt phụ phí, bảng giá, cấn trừ, khung chi tiết trên điện
 * thoại) khai aria-modal nhưng không bẫy tiêu điểm: Tab đi xuyên xuống sổ phía sau lớp nền mờ, Enter bấm được một nút người
 * dùng không thấy. Sửa từng hộp sang <dialog>.showModal() phải viết lại cả cách vẽ và đóng của sáu hộp; module này làm một
 * việc chung: theo dõi DOM, thấy hộp chặn nào đang hiện thì đặt `inert` cho mọi phần tử anh em trên đường từ hộp đó lên
 * <body>, hộp đóng thì gỡ đúng những chỗ mình đã đặt. Esc và trả tiêu điểm vẫn do từng hộp lo như trước.
 *
 * Lớp nền mờ (phần tử anh em không có gì bấm hay focus được, ví dụ .ph-veil, .dx-mask) không bị `inert`: bấm nền vẫn đóng
 * hộp. Hộp nằm trong phần tử bị `hidden` không tính là đang hiện. */
(function () {
  'use strict';
  if (typeof document === 'undefined' || typeof MutationObserver === 'undefined') return;

  const MARK = 'data-modal-inert';
  const FOCUSABLE = 'a[href],button,input,select,textarea,summary,[tabindex],[contenteditable="true"],iframe';
  const SKIP = new Set(['SCRIPT', 'STYLE', 'LINK', 'TEMPLATE', 'META']);

  const shown = element => element.isConnected && !element.closest('[hidden]');
  const interactive = element => element.matches(FOCUSABLE) || Boolean(element.querySelector(FOCUSABLE));

  function sync() {
    const open = [...document.querySelectorAll('[aria-modal="true"]')].filter(shown);
    const top = open.at(-1) ?? null;
    const want = new Set();
    for (let node = top; node && node !== document.body && node.parentElement; node = node.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling === node || SKIP.has(sibling.tagName) || !interactive(sibling)) continue;
        want.add(sibling);
      }
    }
    for (const element of document.querySelectorAll(`[${MARK}]`)) {
      if (want.has(element)) continue;
      element.inert = false;
      element.removeAttribute(MARK);
    }
    for (const element of want) {
      if (element.inert) continue;   // trang đã tự đặt inert: không đánh dấu để khỏi gỡ nhầm
      element.inert = true;
      element.setAttribute(MARK, '');
    }
  }

  // Hộp đóng (hidden = true) rồi trang gọi ngay opener.focus() trong cùng lượt: lúc đó MutationObserver chưa chạy nên opener vẫn
  // inert và focus() không có tác dụng. Phần tử nằm trong vùng mình đã inert mà được gọi focus() thì đồng bộ ngay trước.
  if (typeof HTMLElement !== 'undefined') {
    const focus = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function (...args) {
      if (this.closest?.(`[${MARK}]`)) sync();
      return focus.apply(this, args);
    };
  }

  let queued = false;
  const schedule = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => { queued = false; sync(); });
  };
  const start = () => {
    new MutationObserver(schedule).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'aria-modal'] });
    sync();
  };
  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
  globalThis.CongNoModal = { sync };
})();
