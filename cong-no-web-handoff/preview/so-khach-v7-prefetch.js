/* Sổ khách V7 bản live — bắt đầu GET sổ ngay khi trang mở (MO-SO-NHANH-01, 4/11/2026).
 *
 * Thẻ <script> này đứng đầu <head>, trước CSS và 36 file JS của trang: GET /api/v7/ledger chạy song song với việc tải
 * các file đó thay vì đợi tải xong (đo trên hao 4/11/2026: tải file 330–500 ms, GET sổ 155–670 ms, trước đây cộng dồn).
 * Chỉ bắt đầu một fetch và cất promise ở window.SoKhachV7Prefetch; so-khach-v7-api.js (create().read()) dùng nó đúng một
 * lần cho lần đọc đầu của cùng mã khách, lỗi thì lần đọc sau gọi fetch như thường. Không vẽ, không đọc kết quả ở đây. */
(() => {
  'use strict';
  if (typeof fetch !== 'function' || typeof location === 'undefined' || typeof window === 'undefined') return;
  const customerId = new URLSearchParams(location.search).get('customer');
  if (!customerId) return;
  const response = fetch(`/api/v7/ledger?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
  response.catch(() => {});   // lỗi mạng báo ở lần đọc của trang, không thành "unhandled rejection" ở đây
  window.SoKhachV7Prefetch = { customerId, response };
})();
