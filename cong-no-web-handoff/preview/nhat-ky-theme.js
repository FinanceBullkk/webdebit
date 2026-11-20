// NHAT-KY-01: chế độ Sáng / Tối / Theo máy cho trang Nhật ký (20/11/2026). Nạp trong <head>, chạy trước khi vẽ trang
// để không nháy nền trắng khi đang ở chế độ tối (CSP chỉ cho script từ file nên không viết inline).
// Lựa chọn lưu ở trình duyệt (localStorage "nk-theme"); "auto" theo cài đặt sáng/tối của máy và đổi theo khi máy đổi.
(() => {
  'use strict';
  const KEY = "nk-theme", media = matchMedia("(prefers-color-scheme: dark)"), root = document.documentElement;
  let pick = "auto";
  try { pick = ["light", "dark", "auto"].includes(localStorage.getItem(KEY)) ? localStorage.getItem(KEY) : "auto"; } catch { /* trình duyệt chặn lưu: theo máy */ }
  const apply = () => { root.dataset.nkTheme = pick === "auto" ? (media.matches ? "dark" : "light") : pick; root.dataset.nkPick = pick; };
  media.addEventListener("change", () => { if (pick === "auto") apply(); });
  apply();
  window.nkTheme = {
    get: () => pick,
    set(value) { pick = value; try { localStorage.setItem(KEY, value); } catch { /* bỏ qua */ } apply(); }
  };
})();
