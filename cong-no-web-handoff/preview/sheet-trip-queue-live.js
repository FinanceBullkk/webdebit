(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const customer = new URLSearchParams(location.search).get('customer');
  const query = customer && /^[1-9][0-9]*$/.test(customer) ? `?customer=${customer}` : '';
  fetch(`/api/v7/sheet-queue${query}`, { cache: 'no-store' })
    .then(response => response.ok ? response.json() : response.json().then(value => Promise.reject(Error(value.message || 'Không đọc được hàng chờ'))))
    .then(data => {
      const items = data.items;
      document.querySelector('#meta').textContent = `${items.length} dòng hiển thị · snapshot ${data.snapshot_sha256}`;
      document.querySelector('#rows').innerHTML = items.map(row => `<tr><td>${esc(row.source_row)}</td><td>${esc(row.container)}<br><small>${esc(row.event_date || row.source_date)}</small></td><td>${esc(row.customer_name || 'Chưa khớp')}</td><td class="tag ${row.review_status === 'INVALID' ? 'invalid' : 'review'}">${esc(row.review_status)}</td><td>${esc((row.review_reasons || []).join(', '))}</td></tr>`).join('') || '<tr><td colspan="5">Không có dòng cần xử lý cho khách này.</td></tr>';
    })
    .catch(error => { document.querySelector('#meta').textContent = error.message; });
})();
