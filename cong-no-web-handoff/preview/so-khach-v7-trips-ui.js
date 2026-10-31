/* Sổ khách V7 bản live — bảng chuyến bên trái của mỗi tháng (SO-GON-02): dòng sổ gốc, chuyến web, chuyến Sheet chờ duyệt
 * và nhãn KHÁC trên dòng lệch Sheet. Tách từ renderSnapshot của so-khach-v7-ui.js (31/10/2026, DOM không đổi).
 * Mọi số tiền lấy nguyên từ GET; phần này chỉ định dạng (ARCH-03). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).trips = ctx => {
  'use strict';
  const { root, model, escape, fmt, cell, num, empty, columns, dateText, sheetDay, fieldNames, moved, feeTypeName } = ctx;
  const { shipperCell } = columns;
  const moneyCell = value => /^-?\d+$/.test(value ?? '') ? fmt(value) : (value ?? '');
  const conflictFields = row => row.changed_fields?.length
    ? row.changed_fields.map(field => ({ event_date: 'ngày', carrier: 'hãng tàu', shipper: 'shipper',
      shipper_unavailable: 'thiếu shipper Sheet', origin: 'nơi đi', destination: 'nơi đến', booking: 'booking' })[field] || field).join(', ')
    : ({ OTHER_CUSTOMER: 'khách khác', BASELINE_MATCH_UNRESOLVED: 'bản mốc chưa nối',
      CONTAINER_REUSED_OR_CHANGED: 'container đã dùng', AMBIGUOUS_MATCH: 'nhiều chuyến trùng' })[row.sync_reason] || 'chưa rõ';
  // NHAP-SHEET-01: mọi ô chuyến (web và sổ gốc) sửa đè tại ô, kể cả tháng khóa; bấm STT để xóa hẳn.
  // Đổi ngày sang tháng khác (góp ý 23/10/2026): dòng vừa chuyển tô vàng ở tháng mới (ctx.moved, so-khach-v7-edit-ui.js).
  const movedTag = rowKey => moved.has(rowKey)
    ? `<tr class="moved-note"><td colspan="${columns.trip()}"><span class="moved-tag">↪ Vừa chuyển từ T${Number(moved.get(rowKey).slice(5))}</span></td></tr>`
    : '';
  const infoCell = (kind, id, field, text, classes = '') => `<td class="info-edit ${classes}" data-kind="${kind}" data-id="${escape(id)}" `
    + `data-field="${field}" tabindex="0" role="button" aria-label="Sửa ${fieldNames[field]}">${escape(text)}</td>`;
  const deleteCell = (kind, id, text, what, pick = '') => `<td class="row-delete" data-kind="${kind}" data-id="${escape(id)}" tabindex="0" `
    + `role="button" aria-label="Xóa hẳn ${escape(what)}" title="Bấm để xóa hẳn dòng này">${pick}${escape(text)}</td>`;
  // PHU-PHI-01: cụm cột phụ phí = cột riêng của sổ (0–3, theo fee_columns) + Khác. Số lấy từ fee_lines của server,
  // model cộng để hiện (ARCH-03). Ô cột riêng: bấm gõ số; ô Khác: mở khung chi tiết (so-khach-v7-fee-ui.js).
  const feeCells = (target, what, lines, editable) => {
    const cells = model.feeCells(lines ?? [], ctx.feeColumnIds);
    const own = ctx.feeColumnIds.map((id, index) => `<td class="num fee own${editable ? ' fee-edit' : ''}" data-fee-target="${target}" `
      + `data-fee-type="${id}"${editable ? ` tabindex="0" role="button" aria-label="Sửa ${escape(feeTypeName(id))} ${escape(what)}"` : ''}>`
      + `${cells.own[index] === null ? '' : model.formatVnd(cells.own[index])}</td>`).join('');
    const other = cells.otherCount ? `<span class="fee-sum">${model.formatVnd(cells.otherVnd)}</span><small>${cells.otherCount} khoản</small>`
      : editable ? '<span class="fee-plus">+ thêm</span>' : '';
    return `${own}<td class="num fee fee-other" data-field="other_fee_vnd" data-fee-target="${target}" tabindex="0" role="button" `
      + `aria-label="Chi tiết phụ phí ${escape(what)}">${other}</td>`;
  };
  const feeEmpty = () => ctx.feeColumnIds.map(() => empty('num fee')).join('') + empty('num fee');
  const feePick = (target, what, editable) => editable
    ? `<input type="checkbox" class="fee-pick" data-fee-target="${target}" aria-label="Chọn ${escape(what)} để thêm phụ phí">` : '';

  // Dòng chuyến sổ gốc (bản sao Sheet). `trip.d` là cột Sheet đã đọc; `current` là bản đang dùng khi dòng sửa được.
  // Sheet history in the ledger columns: amounts come from the copy as digit strings; no maths here.
  // The loader resolves every serial date to one reading (dd/mm/yyyy); anything left is text typed in the Sheet ("da tt").
  const curDay = (cur, t) => cur.event_date ? dateText(cur.event_date) : sheetDay(t.raw_date);
  const countedCell = cur => num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd));
  const legacyLocked = (trip, cur, t, stt, unitText) => [cell(stt || '–'), cell(cur.container || 'Phí lẻ'), cell(cur.carrier ?? ''),
    shipperCell(cell(cur.shipper ?? '')), cell(curDay(cur, t)), cell(cur.origin ?? ''), cell(cur.destination ?? ''), num(unitText[0]),
    feeCells(`legacy:${trip.id}`, cur.container || 'phí lẻ', trip.fee_lines, false), countedCell(cur)].join('');
  const legacyEditable = (trip, cur, t, stt, unitText) => {
    const what = cur.container || 'phí lẻ';
    const edit = (field, text, classes) => infoCell('legacy', trip.id, field, text, classes);
    return [deleteCell('legacy', trip.id, stt || '–', `dòng sổ gốc ${what}`, feePick(`legacy:${trip.id}`, what, cur.unit_price_vnd != null)),
      edit('container', cur.container || 'Phí lẻ'), edit('carrier', cur.carrier ?? ''), shipperCell(edit('shipper', cur.shipper ?? '')),
      edit('event_date', curDay(cur, t)), edit('origin', cur.origin ?? ''), edit('destination', cur.destination ?? ''),
      edit('unit_price_vnd', unitText[0], `num ${unitText[1]}`), feeCells(`legacy:${trip.id}`, what, trip.fee_lines, cur.unit_price_vnd != null),
      countedCell(cur)].join('');
  };
  const legacySheet = (trip, t, stt) => [cell(stt), cell(t.container || 'Phí lẻ'), cell(t.carrier ?? ''), shipperCell(cell(t.shipper ?? '')),
    cell(t.date ? dateText(t.date) : sheetDay(t.raw_date)), cell(t.from ?? ''), cell(t.to ?? ''),
    !t.unit_price && (t.flags ?? []).includes('MISSING_PRICE') ? '<td class="num missing">chưa có giá</td>' : num(moneyCell(t.unit_price)),
    feeCells(`legacy:${trip.id}`, t.container || 'phí lẻ', trip.fee_lines, false), num(fmt(trip.source_total_vnd))].join('');
  function legacyTripRow(trip, locked) {
    const t = trip.d;
    const cur = trip.editable && trip.current ? trip.current : null;
    const stt = String(t.stt ?? '').replace(/^(\d+)\.0+$/, '$1');
    // Ô trống trong `current` nghĩa là bản gốc không đọc được thành số/ngày: hiện chữ Sheet, trừ khi đã bị xóa giá.
    const unitText = cur?.unit_price_vnd != null ? [fmt(cur.unit_price_vnd), '']
      : /^\d+$/.test(t.unit_price ?? '') || !t.unit_price && (t.flags ?? []).includes('MISSING_PRICE')
        ? ['chưa có giá', 'missing'] : [moneyCell(t.unit_price), ''];
    const tripCells = cur && locked ? legacyLocked(trip, cur, t, stt, unitText)
      : cur ? legacyEditable(trip, cur, t, stt, unitText) : legacySheet(trip, t, stt);
    const rowKey = trip.id != null ? `legacy-${trip.id}` : '';
    return `<tr class="legacy${moved.has(rowKey) ? ' moved' : ''}"${rowKey ? ` data-row="${escape(rowKey)}"` : ''}>${tripCells}</tr>${movedTag(rowKey)}`;
  }

  // Chuyến web. STT nối tiếp các dòng chuyến từ Sheet của tháng (`sttBase`, dòng Sheet vẽ trước như thứ tự trên Sheet).
  function webTripRow(trip, index, { locked, sttBase }) {
    const pending = trip?.status === 'pending_review';
    const info = !locked && trip?.info_editable === true;
    const infoCells = info
      ? ['container', 'carrier', ...(columns.shipper() ? ['shipper'] : []), 'event_date', 'origin', 'destination'].map(field =>
        infoCell('trip', trip.id, field, field === 'event_date' ? dateText(trip.event_date) : trip[field] ?? '')).join('')
      : `${cell(trip?.container ?? '')}${cell(trip?.carrier ?? '')}${shipperCell(cell(trip?.shipper ?? ''))}${cell(dateText(trip?.event_date))}`
        + `${cell(trip?.origin ?? '')}${cell(trip?.destination ?? '')}`;
    const rowKey = trip ? `trip-${trip.id}` : '';
    const feeEditable = !locked && trip?.editable === true && trip.status === 'confirmed';
    const what = trip?.container || 'phí lẻ';
    const number = sttBase + index + 1;
    const stt = info ? deleteCell('trip', trip.id, trip.is_fee_only ? '–' : number, `chuyến ${what}`, feePick(`trip:${trip.id}`, what, feeEditable))
      : trip && !trip.is_fee_only ? cell(number) : empty();
    const priceText = trip?.is_missing_price ? trip.note === 'Chuyến đồng bộ' ? '' : 'chưa có giá' : fmt(trip?.unit_price_vnd);
    const price = pending || trip?.status === 'rejected' || locked ? num(priceText)
      : trip ? `<td class="num editable ${trip.is_missing_price ? 'missing' : ''}" data-trip="${trip.id}" data-field="unit_price_vnd" tabindex="0" `
        + `role="button" aria-label="Sửa đơn giá chuyến ${index + 1}">${priceText}</td>` : empty('num');
    const amount = !trip ? empty('num') : pending && locked ? num('CHỜ KIỂM')
      : pending ? `<td class="num review-cell"><button type="button" class="review-open" data-trip="${trip.id}" aria-expanded="false" `
        + `aria-label="Kết luận chuyến ${escape(trip.container)} đang CHỜ KIỂM">CHỜ KIỂM</button></td>`
      : trip.status === 'rejected' ? '<td class="num trip-rejected">ĐÃ LOẠI</td>' : num(fmt(trip.amount_vnd));
    return `<tr${rowKey ? ` data-row="${rowKey}"` : ''}${moved.has(rowKey) ? ' class="moved"' : ''}>${stt}
            ${infoCells}
            ${price}
            ${trip ? feeCells(`trip:${trip.id}`, what, trip.fee_lines, feeEditable) : feeEmpty()}
            ${amount}
            </tr>${movedTag(rowKey)}`;
  }

  // Chuyến Sheet chưa vào sổ: CHỜ DUYỆT (dòng mới) hoặc KHÁC (lệch chưa nối được dòng nào trong sổ).
  const sheetPendingRows = rows => rows.map(row => `<tr class="${row.sync_state === 'NEW' ? 'sheet-new' : 'sheet-conflict'}">
          ${empty()}<td>${escape(row.container)}<small>${row.sync_state === 'NEW' ? 'CHỜ DUYỆT' : `KHÁC: ${conflictFields(row)}`}</small></td>`
    + `${cell(row.carrier)}${shipperCell(cell(row.shipper))}${cell(dateText(row.event_date))}${cell(row.origin)}${cell(row.destination)}
          ${empty('num')}${feeEmpty()}${num('–')}${empty('pay pay-start')}${empty('pay')}${empty('pay num')}
          </tr>`).join('');

  // Dòng trong sổ mà Sheet có dữ liệu khác: tô KHÁC và nút Xem (khung đối chiếu ở so-khach-v7-sheet-ui.js).
  function conflictsAfterRender(data) {
    const sheetRows = data.sheet_sync?.items ?? [];
    for (const row of sheetRows.filter(item => item.sync_state === 'CONFLICT' && item.existing_id)) {
      const target = root.querySelector(`[data-row="${row.existing_kind}-${row.existing_id}"]`);
      if (target) {
        target.classList.add('sheet-conflict');
        target.title = 'Chuyến Sheet có dữ liệu khác. Giữ nguyên sổ hiện có.';
        const label = document.createElement('small'); label.textContent = `KHÁC: ${conflictFields(row)}`;
        target.children[1]?.append(label);
        const button = document.createElement('button'); button.type = 'button'; button.className = 'sheet-diff';
        button.dataset.index = String(sheetRows.indexOf(row)); button.textContent = 'Xem';
        button.setAttribute('aria-expanded', 'false');
        target.children[1]?.append(button);
      }
    }
  }

  Object.assign(ctx, { legacyTripRow, webTripRow, sheetPendingRows, conflictsAfterRender });
};
