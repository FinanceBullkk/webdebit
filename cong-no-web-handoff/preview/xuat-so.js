/* Nút "Tải cả sổ" ở Tổng quan (XUAT-SO-01, specs/v7-xuat-ca-so.md): gọi GET /api/v7/xuat-so.xlsx, tải file về máy và báo
   kết quả tự kiểm của máy chủ (header X-Xuat-So: mã, số đếm, mã sổ). Không tính tiền ở đây; file và phép kiểm do máy chủ làm. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.XuatSo = api;
}(typeof self !== 'undefined' ? self : this, function () {
  const PATH = '/api/v7/xuat-so.xlsx';
  // Câu cho từng mã lệch; n là số sổ lệch.
  const PROBLEMS = {
    TONG_QUAN_PHAI_THU: () => 'Còn phải thu trên Tổng quan khác tổng các sổ',
    TONG_QUAN_KHACH_DU: () => 'Khách trả thừa trên Tổng quan khác tổng các sổ',
    SO_LECH_TONG_QUAN: n => `${n} sổ lệch số Tổng quan`,
    SO_LECH_THANG: n => `${n} sổ cộng các tháng không bằng nợ còn lại`,
    PHIEU_CHIA_LECH: n => `${n} sổ có phiếu thu chia không khớp`,
    FILE_LECH: () => 'file ghi ra không khớp sổ',
  };

  function problemText(problem) {
    const say = PROBLEMS[problem.code] ?? (() => `phép kiểm ${problem.code} không đạt`);
    const books = Array.isArray(problem.books) && problem.books.length
      ? ` (sổ ${problem.books.join(', ')}${problem.count > problem.books.length ? '…' : ''})` : '';
    return say(problem.count) + books;
  }

  /** Câu báo sau khi tải xong: { tone: 'ok' | 'bad', text }. `check` là JSON của header X-Xuat-So (có thể thiếu). */
  function summary(check, filename) {
    if (check && check.ok === true) {
      return { tone: 'ok', text: `Đã tải ${filename}: ${check.books} sổ, tự kiểm khớp (tổng các sổ bằng Còn phải thu trên Tổng quan). `
        + 'Cất file vào thư mục dự phòng.' };
    }
    const problems = (check?.problems ?? []).map(problemText);
    const what = problems.length ? problems.join('; ') : 'máy chủ không gửi kết quả tự kiểm';
    return { tone: 'bad', text: `Bản xuất có chỗ lệch: ${what}. File ${filename} vẫn tải về và đã đánh dấu CO-LECH; `
      + 'báo quản trị kiểm trước khi dùng.' };
  }

  /** Câu báo khi không tải được: 429 là đang có lượt khác; còn lại dùng câu của máy chủ nếu có. */
  function failure(status, body) {
    if (status === 429) return { tone: 'wait', text: 'Đang có một lượt xuất khác. Chờ khoảng một phút rồi bấm lại.' };
    const message = typeof body?.message === 'string' && body.message.trim() ? body.message.trim() : 'Thử lại sau ít phút.';
    return { tone: 'bad', text: `Chưa xuất được cả sổ. ${message}` };
  }

  function filenameOf(disposition) {
    const found = /filename="([^"]+)"/.exec(disposition ?? '');
    return found ? found[1] : 'so-web.xlsx';
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function create({ button, status, fetcher = (...args) => fetch(...args), save = saveBlob }) {
    const label = button.querySelector('span');
    const idle = label?.textContent ?? '';
    let running = false;

    function show(view) {
      status.hidden = false;
      status.className = `export-status is-${view.tone}`;
      status.textContent = view.text;
    }

    function busy(on) {
      running = on;
      button.disabled = on;
      button.setAttribute('aria-busy', on ? 'true' : 'false');
      if (label) label.textContent = on ? 'Đang xuất…' : idle;
    }

    async function run() {
      if (running) return;
      busy(true);
      show({ tone: 'busy', text: 'Đang xuất cả sổ… thường mất dưới một phút. Đừng đóng trang.' });
      try {
        const response = await fetcher(PATH, { cache: 'no-store' });
        if (!response.ok) {
          show(failure(response.status, await response.json().catch(() => null)));
          return;
        }
        let check = null;
        try { check = JSON.parse(response.headers.get('X-Xuat-So') ?? 'null'); } catch { check = null; }
        const filename = filenameOf(response.headers.get('Content-Disposition'));
        save(await response.blob(), filename);
        show(summary(check, filename));
      } catch {
        show(failure(0, null));
      } finally {
        busy(false);
      }
    }

    button.addEventListener('click', run);
    return { run };
  }

  return { create, summary, failure, filenameOf, problemText, PATH };
}));
