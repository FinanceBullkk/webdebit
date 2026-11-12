(() => {
  'use strict';
  // THONG-TIN-CTY-01 (specs/v7-thong-tin-cty.md): xem thông tin xuất hóa đơn của khách và tài khoản nhận tiền, đọc từ bản chụp
  // Sheet thông tin khách hàng mà timer trên hao ghi mỗi giờ (GET /api/v7/company-info). Chỉ xem: sửa trên Sheet.
  const F = CongNoFormat;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const LIMIT = 60;   // khách vẽ một lần khi chưa gõ tìm; Sheet có hơn nghìn dòng
  const CJK = /[㐀-鿿]/;
  const filter = $('customer-filter');
  let data = null;

  // Nhãn trên Sheet song ngữ ("公司全称\nACC NAME"): trang hiện phần chữ Latin, đủ thì hiện nguyên.
  const latinLabel = label => String(label).split('\n').filter(line => line.trim() && !CJK.test(line)).join(' ') || label;
  const copyButton = (text, what) => `<button type="button" class="ttc-copy" data-copy="${esc(text)}" aria-label="Chép ${esc(what)}">Chép</button>`;
  const readAt = iso => {
    const at = new Date(iso);
    if (!iso || Number.isNaN(at.getTime())) return '—';
    const part = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }).formatToParts(at);
    const get = type => part.find(item => item.type === type)?.value ?? '';
    return `Theo Sheet lúc ${get('hour')}:${get('minute')} ${get('day')}/${get('month')}`;
  };

  function drawAccounts() {
    $('accounts').innerHTML = data.accounts.length ? data.accounts.map(account => `<article class="ttc-account">
      <h3>${esc(account.label || account.bank || 'Tài khoản')}</h3>
      <dl>${account.lines.map(line => `<div${line.value === account.account ? ' class="is-number"' : ''}><dt>${esc(latinLabel(line.label))}</dt><dd>${esc(line.value)}${
        line.value === account.account ? copyButton(line.value, 'số tài khoản') : ''}</dd></div>`).join('')}</dl></article>`).join('')
      : '<p class="empty">Sheet chưa có tài khoản nào.</p>';
  }

  function drawCustomers() {
    const raw = filter.value.trim();
    const loose = F.fold(raw), exact = F.foldText(raw);
    const found = raw ? data.customers.filter(item => [item.shipper, item.invoice].some(value => (loose && F.fold(value).includes(loose)) || F.foldText(value).includes(exact)))
      : data.customers;
    const shown = found.slice(0, LIMIT);
    const total = data.customers.length.toLocaleString('vi-VN');
    $('customer-count').textContent = raw ? `${found.length.toLocaleString('vi-VN')} / ${total} khách` : found.length > LIMIT ? `${LIMIT} / ${total} khách, gõ để tìm` : `${total} khách`;
    $('customers').innerHTML = shown.length ? `<ul class="ttc-list">${shown.map(item => `<li class="ttc-customer">
      <h3>${esc(item.shipper)}</h3>
      <div class="ttc-block"><span class="ttc-k">Thông tin xuất hóa đơn</span>${item.invoice ? `<p>${esc(item.invoice)}</p>${copyButton(item.invoice, `thông tin xuất hóa đơn ${item.shipper}`)}` : '<p class="muted">—</p>'}</div>
      <div class="ttc-block"><span class="ttc-k">Ngân hàng của khách</span>${item.bank ? `<p>${esc(item.bank)}</p>` : '<p class="muted">—</p>'}</div></li>`).join('')}</ul>`
      : `<p class="empty">${raw ? `Không có khách nào khớp "${esc(raw)}".` : 'Sheet chưa có khách nào.'}</p>`;
  }

  function draw() {
    $('read-at').textContent = data.available ? readAt(data.read_at) : '—';
    if (!data.available) {
      $('customers').innerHTML = '<p class="empty">Chưa có bản đọc từ Sheet thông tin khách hàng. Máy chủ chưa bật việc đọc Sheet này.</p>';
      $('accounts').innerHTML = '';
      $('customer-count').textContent = '';
      return;
    }
    drawAccounts();
    drawCustomers();
  }

  async function load() {
    $('refresh-data').disabled = true;
    try {
      const response = await fetch('/api/v7/company-info', { cache: 'no-store' });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body) throw Error(body?.message || 'Không đọc được Thông tin cty.');
      data = body;
      $('error').hidden = true;
      draw();
    } catch (error) {
      $('error').textContent = `${error.message} Bấm làm mới để thử lại.`;
      $('error').hidden = false;
      if (!data) $('customers').innerHTML = '';
    } finally {
      $('refresh-data').disabled = false;
      document.body.dataset.loaded = '1';   // test đợi lượt đọc đầu xong, kể cả khi lỗi
    }
  }

  const query = new URLSearchParams(location.search);
  filter.value = query.get('q') ?? '';
  filter.addEventListener('input', () => {
    const url = new URL(location.href);
    if (filter.value.trim()) url.searchParams.set('q', filter.value.trim()); else url.searchParams.delete('q');
    history.replaceState(null, '', url);
    if (data?.available) drawCustomers();
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('.ttc-copy');
    if (!button) return;
    try { await navigator.clipboard.writeText(button.dataset.copy); button.textContent = 'Đã chép'; }
    catch { button.textContent = 'Không chép được'; }
    setTimeout(() => { button.textContent = 'Chép'; }, 1500);
  });
  $('refresh-data').addEventListener('click', load);
  load();
})();
