/* Đội xe: phần dùng chung của các màn (DOI-XE-CAU-TRUC-01, gói F1; trước đó chép đôi ở doi-xe-ui.js và doi-xe-thu-ui.js).
 * Gồm: đọc JSON, gửi lệnh ghi kèm mã yêu cầu chống ghi trùng, khung `ghi` (khóa bấm lặp, giữ câu báo tới khi đọc lại xong),
 * thông báo, giữ ô đang gõ khi vẽ lại, và địa chỉ giữa các mục (giữ tháng đang chọn khi đổi mục). Không tính tiền, không biết màn
 * nào gọi mình: mỗi màn truyền trạng thái S và hàm vẽ, tải của nó vào `tao`. Chỗ hai màn khác nhau (tiền tố mã dự phòng, câu báo
 * mất mạng, thời gian hiện câu báo, mã lỗi phải tải lại) là tham số, không gộp. Test ở test-doi-xe-chung.js. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DoiXeChung = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  'use strict';

  // ---------- Địa chỉ giữa các mục ----------
  // Tháng trong địa chỉ là YYYY-MM; trong trạng thái của màn là YYYY-MM-01. Chỉ mang theo tháng hợp lệ (01–12).
  const THANG_TRANG_THAI = /^\d{4}-(0[1-9]|1[0-2])-01$/;
  const thangUrl = thang => (typeof thang === 'string' && THANG_TRANG_THAI.test(thang) ? thang.slice(0, 7) : null);
  // Địa chỉ của ba mục trên đầu trang: Người và xe, Bảng kê gửi HTH, Bảng giá. Không có tháng hợp lệ thì như mở thẳng.
  // homNay (YYYY-MM-DD, nếu biết) để bỏ tháng mà trang đích không nhận.
  const TRANG = { nguoi: '/doi-xe.html', bangke: '/doi-xe-bang-ke.html', gia: '/doi-xe-bang-ke.html' };
  function duongDanMuc(muc, thang, homNay) {
    if (!(muc in TRANG)) throw new RangeError(`Mục Đội xe không có: ${muc}`);
    const q = new URLSearchParams();
    if (muc === 'gia') q.set('man', 'gia');
    const t = thangUrl(thang);
    // Người và xe (get_tong, get_so) từ chối tháng sau hôm nay; Bảng kê cho xem tới tháng sau. Biết hom_nay thì không mang tháng sau sang đó.
    const quaHan = muc === 'nguoi' && typeof homNay === 'string' && t !== null && thang > homNay;
    if (t && !quaHan) q.set('thang', t);
    const s = q.toString();
    return TRANG[muc] + (s ? `?${s}` : '');
  }

  // ---------- Giữ ô đang gõ khi vẽ lại ----------
  function withFocus(fn) {
    const el = document.activeElement;
    const key = el?.dataset?.f;
    const pos = key && typeof el.selectionStart === 'number' ? [el.selectionStart, el.selectionEnd] : null;
    fn();
    if (key) {
      const again = document.querySelector(`[data-f="${CSS.escape(key)}"]`);
      if (again) { again.focus(); if (pos && typeof again.setSelectionRange === 'function') again.setSelectionRange(...pos); }
    }
  }

  /* Mạng, ghi và thông báo của một màn. `o`:
   *   S         trạng thái của màn; dùng các khóa busy, toast, giuBao
   *   draw      vẽ lại; load  đọc lại số liệu (trả Promise)
   *   toastBox  phần tử hiện thông báo; esc  hàm thoát HTML
   *   tienTo    tiền tố mã yêu cầu dự phòng khi trình duyệt không có crypto.randomUUID
   *   matMang   câu báo khi gửi lệnh mà mất kết nối
   *   chuaRo    câu báo khi máy chủ trả 2xx nhưng thân không đọc được (mặc định dùng matMang)
   *   toastMs   số ms câu báo tự tắt
   *   taiLai    mã lỗi của máy chủ mà màn phải đọc lại số liệu ngay sau khi báo */
  // Máy chủ trả lỗi mà không có câu (proxy trả trang HTML): nói chuyện gì xảy ra và cần làm gì, không hiện mã HTTP trần
  // (audit giao diện 23/11/2026 F3; mục 4.6 audit UX).
  function loiMayChu(status) {
    if (status === 401 || status === 403) return 'Tài khoản này chưa được cấp quyền.';
    if (status >= 500) return 'Máy chủ đang bận hoặc vừa khởi động lại. Chờ ít phút rồi bấm lại.';
    return 'Máy chủ từ chối yêu cầu. Tải lại trang rồi thử lại.';
  }

  function tao(o) {
    const { S, draw, load, toastBox, esc, tienTo, matMang, chuaRo, toastMs } = o;
    const taiLai = new Set(o.taiLai);
    const keys = new Map();   // nội dung lệnh → mã yêu cầu, giữ tới khi máy chủ trả lời được

    async function getJson(url) {
      let r;
      try {
        r = await globalThis.fetch(url, { cache: 'no-store' });
      } catch {
        throw Object.assign(Error(matMang), { code: 'NETWORK' });
      }
      const body = await r.json().catch(() => null);
      if (!r.ok) throw Object.assign(Error(body?.message || loiMayChu(r.status)), { code: body?.error, status: r.status });
      return body;
    }
    // Cùng đường dẫn và nội dung thì dùng lại mã: bấm lặp hoặc gửi lại sau mất mạng, máy chủ trả kết quả cũ thay vì ghi lần hai.
    // Máy chủ đã trả lời (thành công hay lỗi) thì bỏ mã, trừ 503 (chưa rõ đã xử lý chưa nên giữ mã).
    async function post(path, body) {
      const sig = `${path} ${JSON.stringify(body)}`;
      if (!keys.has(sig)) keys.set(sig, globalThis.crypto?.randomUUID?.() ?? `${tienTo}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
      let r;
      try {
        r = await globalThis.fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: keys.get(sig), ...body }) });
      } catch {
        throw Object.assign(Error(matMang), { code: 'NETWORK' });
      }
      let doc = true;
      const out = await r.json().catch(() => { doc = false; return null; });
      if (!r.ok) {
        if (r.status !== 503) keys.delete(sig);
        throw Object.assign(Error(out?.message || loiMayChu(r.status)), { code: out?.error, status: r.status });
      }
      // Trả lời 2xx mà thân không đọc được: chưa biết kết quả, nên giữ mã như khi mất mạng để bấm lại không ghi lần hai
      // (máy chủ trả kết quả cũ). Bỏ mã ở đây thì lần bấm lại sinh mã mới và có thể ghi hai lần.
      if (!doc) throw Object.assign(Error(chuaRo ?? matMang), { code: 'BAD_RESPONSE', status: r.status });
      keys.delete(sig);
      return out;
    }

    function drawToast() {
      toastBox.hidden = !S.toast;
      toastBox.className = `dx-toast ${S.toast?.loai ?? ''}`;
      toastBox.innerHTML = S.toast ? `<span>${esc(S.toast.text)}</span><button type="button" data-act="dong-toast" aria-label="Đóng thông báo">✕</button>` : '';
    }
    function bao(text, loai = 'ok') {
      if (S.giuBao) { S.giuBao.push([text, loai]); return; }
      S.toast = { text, loai, n: (S.toast?.n ?? 0) + 1 };
      const n = S.toast.n;
      drawToast();
      globalThis.setTimeout(() => { if (S.toast?.n === n) { S.toast = null; drawToast(); } }, toastMs);
    }
    // Khung ghi: một lệnh một lúc (bấm lặp bị bỏ), câu báo kết quả chỉ hiện sau khi sổ đọc lại xong để người dùng thấy câu báo
    // cùng lúc với số mới. `ok(out)` chạy ngay sau khi máy chủ trả lời (có thể trả Promise); lỗi thì báo và tải lại nếu mã lỗi
    // nằm trong `taiLai`. Trả kết quả của máy chủ, hoặc null khi bị bỏ hay lỗi.
    async function ghi(path, body, ok) {
      if (S.busy) return null;
      S.busy = true;
      draw();
      try {
        const out = await post(path, body);
        S.giuBao = [];
        if (ok) { const r = ok(out); if (r && typeof r.then === 'function') await r; }
        await load();
        const giu = S.giuBao;
        S.giuBao = null;
        for (const [text, loai] of giu) bao(text, loai);
        return out;
      } catch (e) {
        S.giuBao = null;
        bao(e.message, 'err');
        if (taiLai.has(e.code)) await load();
        return null;
      } finally {
        S.busy = false;
        draw();
        for (const r of choRanh.splice(0)) r();
      }
    }
    // Hàng chờ (audit DX-02): sửa ô liền tay (Tab rồi gõ ô sau) khi lệnh trước chưa xong thì không bị bỏ như `ghi`, mà chờ tới lượt.
    // Việc chạy theo thứ tự đã xếp, mỗi việc khi không lệnh ghi nào đang chạy; `fn` đọc số "đang thấy" ngay lúc chạy (sổ đã tải lại
    // sau lệnh trước), nên hai lần sửa cùng một ô không tự gây CHANGED. Trả kết quả của `fn`.
    let hang = Promise.resolve();
    const choRanh = [];
    function xep(fn) {
      const p = hang.then(async () => {
        while (S.busy) await new Promise(r => { choRanh.push(r); });
        return fn();
      });
      hang = p.catch(() => null);
      return p;
    }
    return { getJson, post, bao, ghi, xep, drawToast };
  }

  return { thangUrl, duongDanMuc, withFocus, tao, loiMayChu };
}));
