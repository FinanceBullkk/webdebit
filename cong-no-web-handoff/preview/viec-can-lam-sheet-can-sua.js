/* Khối "Sheet cần sửa" (KIEM-TAB-01 đợt 3d, specs/v7-sheet-can-sua.md): khi tab Sheet của khách hỏng, bảng đối chiếu không có khoản để
ghi mà chỉ nói chỗ sai: câu thường, ô, cách sửa, và bản dựng lại vùng ô quanh ô lỗi (đọc theo yêu cầu qua /api/v7/sheet/vung-o).
Chỉ vẽ chuỗi HTML; không đụng DOM, không ghi gì. Mọi chữ lấy từ server đều qua `esc`. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SheetCanSua = api;
}(typeof self !== 'undefined' ? self : this, () => {
  const KIND_TITLE = {
    row_shift: 'Tiền lệch một dòng',
    chain_break: 'Số cuối tháng bị gãy',
    negative_receipt: 'Số âm ở cột thu',
    duplicate_container: 'Container ghi hai lần',
  };
  const ISSUE_TEXT = {
    MISSING_TRIP_AMOUNT: 'Có chuyến chưa ghi số tiền',
    INVALID_RECEIPT_AMOUNT: 'Có ô thu không đọc được',
    MISSING_MONTH: 'Không thấy khối tháng',
    SOURCE_LAYOUT_UNSUPPORTED: 'Bố cục tab máy chưa đọc được',
  };
  const clock = iso => new Date(iso).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });

  const titleOf = finding => KIND_TITLE[finding.kind] ?? ISSUE_TEXT[finding.kind] ?? 'Tab chưa đọc được';
  const levelOf = finding => (finding.level === 'warning' ? 'warning' : 'error');
  const hasCells = finding => Array.isArray(finding.cells) && finding.cells.length > 0;
  const key = (id, index) => `${id}:${index}`;

  // Cột trống liên tiếp là một cột hẹp "…"; ô gộp chỉ giữ khi nằm gọn trong các cột đang hiện.
  function gridHtml(region, esc) {
    const groups = region.column_groups;
    const shown = new Map();   // chỉ số cột -> chỉ số cột hiện
    groups.forEach((group, index) => group.cols.forEach(col => shown.set(col, index)));
    const mergeAt = new Map(), covered = new Set();
    for (const merge of region.merges ?? []) {
      const first = shown.get(merge.c1), last = shown.get(merge.c2 - 1);
      const whole = groups.slice(first, last + 1).every(group => !group.collapsed);
      if (first === undefined || last === undefined || !whole || (merge.r2 - merge.r1) * (merge.c2 - merge.c1) < 2) continue;
      mergeAt.set(`${merge.r1}:${merge.c1}`, merge);
      for (let r = merge.r1; r < merge.r2; r += 1) for (let c = merge.c1; c < merge.c2; c += 1) if (r !== merge.r1 || c !== merge.c1) covered.add(`${r}:${c}`);
    }
    const marks = new Map((region.marks ?? []).map(mark => [`${mark.row}:${mark.col}`, mark]));
    const head = `<tr><th class="sf-corner" scope="col"><span class="sr-only">Dòng</span></th>${groups.map(group => (group.collapsed
      ? '<th class="sf-gap" scope="col" aria-label="cột trống">…</th>'
      : `<th scope="col" style="min-width:${Math.max(36, Math.min(160, region.widths[group.cols[0]] ?? 80))}px">${esc(region.col_letters[group.cols[0]])}</th>`)).join('')}</tr>`;
    const body = region.cells.map((line, r) => {
      const cells = groups.map(group => {
        if (group.collapsed) return '<td class="sf-gap" aria-hidden="true">…</td>';
        const c = group.cols[0];
        if (covered.has(`${r}:${c}`)) return '';
        const cell = line[c], mark = marks.get(`${r}:${c}`), merge = mergeAt.get(`${r}:${c}`);
        const classes = ['sf-cell'];
        if (mark) classes.push(`sf-${mark.level === 'error' ? 'error' : mark.level === 'suspect' ? 'suspect' : 'warning'}`);
        if (cell.b) classes.push('sf-bold');
        if (cell.al === 'RIGHT' || (!cell.al && /^[-\d.,\s]+$/.test(cell.v) && cell.v.trim())) classes.push('sf-right');
        else if (cell.al === 'CENTER') classes.push('sf-center');
        const span = merge ? ` colspan="${shown.get(merge.c2 - 1) - shown.get(merge.c1) + 1}" rowspan="${merge.r2 - merge.r1}"` : '';
        const style = cell.bg ? ` style="background:${esc(cell.bg)}"` : '';
        const note = mark ? ` title="${esc(mark.text)}" data-sc-mark="${esc(mark.cell)}"` : '';
        const formula = cell.f ? `<span class="sf-formula" title="${esc(cell.f)}">ƒ</span>` : '';
        return `<td class="${classes.join(' ')}"${span}${style}${note}>${esc(cell.v)}${formula}</td>`;
      }).join('');
      return `<tr><th scope="row" class="sf-rowno">${region.first_row + r}</th>${cells}</tr>`;
    }).join('');
    return `<div class="sf-scroll" tabindex="0" role="region" aria-label="Vùng ô trên Sheet, cuộn ngang được"><table class="sf-grid"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  }

  function sampleHtml(sample, esc) {
    if (!sample) return '';
    const now = sample.has_formula ? `đang là <code>${esc(sample.current)}</code>` : sample.current ? `đang là số gõ tay <code>${esc(sample.current)}</code>, không phải công thức` : 'đang để trống';
    return `<p class="sf-sample">Các khối tháng khác dùng công thức <code>${esc(sample.sample)}</code>; ô này ${now}.</p>`;
  }

  function regionHtml(id, index, entry, esc) {
    const attr = `${id}:${index}`;
    if (entry === undefined) return `<p class="loading sf-loading" role="status">Đang đọc Sheet…</p>`;
    if (entry === null) return `<p class="sf-failed" role="status">Chưa tải được hình Sheet. Chỗ sai vẫn đúng như đã nói ở trên. <button type="button" class="btn" data-sc-refresh="${esc(attr)}">Thử lại</button></p>`;
    const marks = entry.region.marks ?? [];
    const notes = marks.length ? `<ul class="sf-notes">${marks.map(mark => `<li class="sf-note sf-${mark.level === 'error' ? 'error' : mark.level === 'suspect' ? 'suspect' : 'warning'}"><strong>${esc(mark.cell)}</strong> ${esc(mark.text)}</li>`).join('')}</ul>` : '';
    return `<div class="sf-region">${gridHtml(entry.region, esc)}<div class="sf-meta"><span>Đọc lúc ${esc(clock(entry.read_at))}</span>`
      + `<button type="button" class="btn" data-sc-refresh="${esc(attr)}">Đọc lại</button>`
      + `<a class="btn" href="${esc(entry.open_url)}" target="_blank" rel="noopener">Mở ô này trên Sheet</a>`
      + `<span class="sf-legend"><i class="sf-key sf-error"></i>ô lỗi <i class="sf-key sf-suspect"></i>ô nghi</span></div>${sampleHtml(entry.sample, esc)}${notes}</div>`;
  }

  function cardHtml(id, index, finding, state, esc) {
    const open = state.regionOpen?.has(key(id, index));
    const cells = hasCells(finding) ? `<span class="sf-cells">${finding.cells.map(cell => `<b>${esc(cell)}</b>`).join(', ')}</span>` : '';
    const toggle = hasCells(finding)
      ? `<button type="button" class="btn" data-sc-view="${esc(key(id, index))}" aria-expanded="${open ? 'true' : 'false'}">${open ? 'Ẩn vùng ô' : 'Xem vùng ô'}</button>` : '';
    const detail = finding.message ?? (finding.count ? `${titleOf(finding)} (${finding.count} chỗ).` : titleOf(finding));
    return `<article class="sf-card sf-${levelOf(finding)}" data-sc-finding="${index}"><header><h3>${esc(titleOf(finding))}</h3>${cells}${toggle}</header>`
      + `<p class="sf-message">${esc(detail)}</p>${finding.fix ? `<p class="sf-fix"><strong>Cách sửa:</strong> ${esc(finding.fix)}</p>` : ''}`
      + `${open && hasCells(finding) ? regionHtml(id, index, state.region?.get(key(id, index)), esc) : ''}</article>`;
  }

  // Khối của một khách có `blocked` (tab không lành hoặc máy đang giữ khách); `state` có `regionOpen` (Set khóa) và `region` (Map khóa -> bản đọc).
  function html(id, statement, state, { esc }) {
    const blocked = statement.blocked;
    const findings = blocked.findings ?? [];
    const lead = findings.length
      ? `<strong>Tab Sheet của khách này cần sửa trước khi web ghi tiền.</strong> ${findings.length === 1 ? '1 chỗ' : `${findings.length} chỗ`}.`
      : '<strong>Máy đang giữ khách này vì Sheet có chỗ chưa đọc được.</strong> Chưa chỉ ra được ô cụ thể.';
    const held = blocked.held && !findings.length && Object.keys(blocked.held_reasons ?? {}).length
      ? `<p class="sf-codes">Mã lỗi của máy: ${Object.entries(blocked.held_reasons).map(([code, n]) => `${esc(code)}${n > 1 ? ` ×${n}` : ''}`).join(', ')}.</p>` : '';
    return `<section class="sheet-fix" aria-label="Sheet cần sửa"><p class="sf-lead">${lead} Web không ghi gì lên Sheet: sửa trên Sheet, web đọc lại sau khoảng 15 phút.</p>${held}`
      + `${findings.map((finding, index) => cardHtml(id, index, finding, state, esc)).join('')}</section>`;
  }

  return { html, gridHtml, regionHtml, titleOf, key, hasCells };
}));
