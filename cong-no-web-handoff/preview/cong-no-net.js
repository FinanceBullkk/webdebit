/* Đọc và gửi JSON tới API, lỗi luôn là câu tiếng Việt (audit giao diện 23/11/2026, F3).
 *
 * Trước đây mỗi trang tự gọi fetch rồi in `error.message` khi hỏng: mất mạng thì người dùng thấy "Failed to fetch"
 * (Chrome) hay "Load failed" (Safari trên iPhone), proxy trả trang HTML 502 thì thấy "Unexpected token '<' … is not
 * valid JSON". Mục 4.6 của docs/ux-audit-2026-10-31.md cấm đúng điều này: câu lỗi theo mẫu "chuyện gì đã xảy ra · cần
 * làm gì", không bao giờ hiện chuỗi của trình duyệt hay mã lỗi.
 *
 *   CongNoNet.fetchJson(url, { what: 'bảng giá' })          → dữ liệu JSON, hoặc ném Error có câu tiếng Việt
 *   CongNoNet.postJson(url, body, { what: 'quyết định' })    → như trên, gửi POST body JSON
 *   CongNoNet.messageOf(error, 'Không lưu được.')           → câu hiện cho người dùng từ một lỗi bất kỳ
 *   CongNoNet.customers()                                   → thân GET /api/v7/customers, mỗi trang đọc một lần (dùng chung)
 *   CongNoNet.fetchResponse(url, { what, fetcher })         → Response như fetch, chỉ đổi lỗi mạng thành câu tiếng Việt
 *   CongNoNet.readJson(response, what)                      → response.json(), thân hỏng thành câu tiếng Việt
 *   (hai hàm cuối cho chỗ tự xét response.ok với câu riêng của mình)
 *
 * Lỗi ném ra có `code`: 'NETWORK' (không tới được máy chủ, kể cả quá hạn), 'BAD_BODY' (máy chủ trả thứ không đọc được),
 * hoặc mã `error` của API (ví dụ 'STALE_LEDGER'); có `status` khi máy chủ đã trả lời. Lỗi API giữ `message` của máy chủ
 * (đã là tiếng Việt) và `data` là cả thân trả về.
 *
 * Không dùng cho lệnh ghi tiền có khóa chống trùng: các đường đó (so-khach-v7-api.js, viec-can-lam.js, doi-xe-chung.js)
 * phân biệt "chưa rõ đã ghi" với "chưa ghi" và giữ khóa để Thử lại; hàm ở đây chỉ báo lỗi, không biết khóa nào. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CongNoNet = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const OFFLINE = 'mất kết nối tới máy chủ. Kiểm tra mạng rồi bấm lại.';

  // Chuỗi của trình duyệt khi fetch hỏng hoặc bị ngắt (Chrome, Safari, Firefox, Node).
  const BROWSER_TEXT = /Failed to fetch|Load failed|NetworkError|network error|fetch failed|The operation was aborted|signal timed out|signal is aborted/i;

  function fail(message, extra) {
    return Object.assign(Error(message), extra);
  }

  async function fetchResponse(url, options = {}) {
    const { what = 'dữ liệu', fetcher = globalThis.fetch, timeoutMs, ...init } = options;
    if (timeoutMs && !init.signal && typeof AbortSignal !== 'undefined' && AbortSignal.timeout) init.signal = AbortSignal.timeout(timeoutMs);
    try {
      return await fetcher(url, { cache: 'no-store', ...init });
    } catch {
      throw fail(`Không tải được ${what}: ${OFFLINE}`, { code: 'NETWORK' });
    }
  }

  // Thân không phải JSON (trang HTML 502 của proxy) là SyntaxError; lỗi khác khi đọc thân là đứt mạng giữa chừng.
  async function readJson(response, what = 'dữ liệu') {
    try {
      return await response.json();
    } catch (error) {
      if (error?.name === 'SyntaxError') {
        throw fail(`Không đọc được ${what} máy chủ trả về. Bấm lại sau ít phút.`, { code: 'BAD_BODY', status: response.status });
      }
      throw fail(`Không tải được ${what}: ${OFFLINE}`, { code: 'NETWORK', status: response.status });
    }
  }

  async function fetchJson(url, options = {}) {
    const what = options.what ?? 'dữ liệu';
    const response = await fetchResponse(url, options);
    let data = null;
    let readable = true;
    try { data = await readJson(response, what); } catch (error) {
      if (error.code === 'NETWORK' || response.ok) throw error;
      readable = false;
    }
    if (!response.ok) {
      if (readable && data && typeof data.message === 'string' && data.message) {
        throw fail(data.message, { code: data.error ?? 'HTTP', status: response.status, data });
      }
      const why = response.status === 401 || response.status === 403
        ? 'tài khoản này chưa được cấp quyền.'
        : response.status >= 500 ? 'máy chủ đang bận hoặc đang khởi động lại. Chờ ít phút rồi bấm lại.' : 'máy chủ từ chối yêu cầu.';
      throw fail(`Không tải được ${what}: ${why}`, { code: readable && data?.error ? data.error : 'HTTP', status: response.status, data });
    }
    return data;
  }

  function postJson(url, body, options = {}) {
    const { headers, ...rest } = options;
    return fetchJson(url, { ...rest, method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  }

  // Câu cho người dùng từ một lỗi bất kỳ: lỗi đã qua fetchJson giữ nguyên; lỗi gốc của trình duyệt (TypeError của fetch,
  // SyntaxError của response.json(), AbortError) đổi thành câu mất kết nối; lỗi khác giữ câu của nó hoặc lấy `fallback`.
  function messageOf(error, fallback = 'Có lỗi, chưa làm được. Bấm lại.') {
    if (!error) return fallback;
    // Mã chữ là lỗi đã qua module này hoặc lỗi API; DOMException (AbortError) cũng có `code` nhưng là số.
    if (typeof error.code === 'string') return error.message || fallback;
    const text = String(error.message ?? '');
    if (error.name === 'SyntaxError' || /is not valid JSON|Unexpected (token|end of JSON)|JSON\.parse/i.test(text)) {
      return 'Máy chủ trả về dữ liệu không đọc được. Bấm lại sau ít phút.';
    }
    if (error.name === 'AbortError' || error.name === 'TimeoutError' || (error.name === 'TypeError' && !text) || BROWSER_TEXT.test(text)) {
      return `Không làm được: ${OFFLINE}`;
    }
    return text || fallback;
  }

  // Danh sách khách: trước 23/11/2026 mỗi trang gọi /api/v7/customers 2–4 lần lúc mở (menu, presence, sổ; Máy chạy bốn lần,
  // audit giao diện F7). Các phần cùng trang dùng chung một lần đọc: lời gọi đang chạy hoặc kết quả chưa quá 60 giây thì trả lại
  // đúng promise đó; lỗi thì bỏ để lần sau đọc lại. `fresh: true` khi vừa đổi danh sách (gán mặt hàng, tạo sổ).
  let customersCache = null;
  function customers({ fresh = false, fetcher } = {}) {
    const now = Date.now();
    if (!fresh && customersCache && now - customersCache.at < 60_000) return customersCache.promise;
    const promise = fetchJson('/api/v7/customers', { what: 'danh sách khách', fetcher });
    customersCache = { at: now, promise };
    promise.catch(() => { if (customersCache?.promise === promise) customersCache = null; });
    return promise;
  }

  return { fetchJson, postJson, fetchResponse, readJson, messageOf, customers };
});
