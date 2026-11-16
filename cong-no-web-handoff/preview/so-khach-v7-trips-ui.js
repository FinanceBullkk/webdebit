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
    : ({ OTHER_CUSTOMER: 'khách khác', OTHER_BOOK_LEGACY: 'đã có ở sổ gốc của sổ khác', BASELINE_MATCH_UNRESOLVED: 'bản mốc chưa nối',
      AMBIGUOUS_MATCH: 'nhiều chuyến trùng' })[row.sync_reason] || 'chưa rõ';
  // CHUYEN-KHONG-HOI-01: container đã có trong sổ, tab khách chưa có dòng riêng. Chỉ để xem: không nút, không tính là việc.
  const WAITING_WHY = 'Container này đã có trong sổ và tab khách trên Sheet chưa có dòng riêng cho chuyến này. '
    + 'Không cần làm gì trên web: tab có dòng riêng thì dòng này thành chuyến mới như thường.';
  // NHAP-SHEET-01: mọi ô chuyến (web và sổ gốc) sửa đè tại ô, kể cả tháng khóa; bấm STT để xóa hẳn.
  // Đổi ngày sang tháng khác (góp ý 23/10/2026): dòng vừa chuyển tô vàng ở tháng mới (ctx.moved, so-khach-v7-edit-ui.js).
  const movedTag = rowKey => moved.has(rowKey)
    ? `<tr class="moved-note"><td colspan="${columns.trip()}"><span class="moved-tag">↪ Vừa chuyển từ T${Number(moved.get(rowKey).slice(5))}</span></td></tr>`
    : '';
  const infoCell = (kind, id, field, text, classes = '') => {
    const tag = ['origin', 'destination'].includes(field) ? 'span' : 'td';
    return `<${tag} class="info-edit ${classes}" data-kind="${kind}" data-id="${escape(id)}" `
    + `data-field="${field}" tabindex="0" role="button" aria-label="Sửa ${fieldNames[field]}">${escape(text)}</${tag}>`;
  };
  const route = (origin, destination) => `<td class="route-cell">${origin}<span class="route-arrow" aria-hidden="true"> → </span>${destination}</td>`;
  const routeText = (origin, destination) => route(`<span data-field="origin">${escape(origin)}</span>`, `<span data-field="destination">${escape(destination)}</span>`);
  const deleteCell = (kind, id, text, what, pick = '') => `<td class="row-delete" data-kind="${kind}" data-id="${escape(id)}" tabindex="0" `
    + `role="button" aria-label="Xóa hẳn ${escape(what)}" title="Bấm để xóa hẳn dòng này">${pick}${escape(text)}</td>`;
  // PHU-PHI-01: cụm cột phụ phí = cột riêng của sổ (0–3, theo fee_columns) + Khác. Số lấy từ fee_lines của server,
  // model cộng để hiện (ARCH-03). Ô cột riêng: bấm gõ số; ô Khác: mở khung chi tiết (so-khach-v7-fee-ui.js).
  const feeCells = (target, what, lines, editable) => {
    const cells = model.feeCells(lines ?? [], ctx.feeColumnIds);
    const own = ctx.feeColumnIds.map((id, index) => `<td class="num fee own${editable ? ' fee-edit' : ''}" data-fee-target="${target}" `
      + `data-fee-type="${id}"${editable ? ` tabindex="0" role="button" aria-label="Sửa ${escape(feeTypeName(id))} ${escape(what)}"` : ''}>`
      + `${cells.own[index] === null ? '' : model.formatVnd(cells.own[index])}</td>`).join('');
    // SO-GON-04 (P0-4): ô Khác trống ghi "–"; "+ thêm" chỉ hiện khi rê chuột, đứng ở dòng hoặc tick chọn dòng (CSS).
    // SO-GON-05: ô có khoản chỉ hiện số (hàng đều một dòng); số khoản ở chữ rê chuột và nhãn đọc màn hình.
    const other = cells.otherCount ? `<span class="fee-sum">${model.formatVnd(cells.otherVnd)}</span>`
      : editable ? '<span class="fee-dash" aria-hidden="true">–</span><span class="fee-plus">+ thêm</span>' : '';
    const count = cells.otherCount ? ` (${cells.otherCount} khoản)` : '';
    return `${own}<td class="num fee fee-other" data-field="other_fee_vnd" data-fee-target="${target}" tabindex="0" role="button" `
      + `${count ? `title="Phụ phí khác${count}" ` : ''}aria-label="Chi tiết phụ phí ${escape(what)}${count}">${other}</td>`;
  };
  const feeEmpty = () => ctx.feeColumnIds.map(() => empty('num fee')).join('') + empty('num fee');
  const feePick = (target, what, editable) => editable
    ? `<input type="checkbox" class="fee-pick" data-fee-target="${target}" aria-label="Chọn ${escape(what)} để thêm phụ phí">` : '';

  // Dòng chuyến sổ gốc (bản sao Sheet). `trip.d` là cột Sheet đã đọc; `current` là bản đang dùng khi dòng sửa được.
  // Sheet history in the ledger columns: amounts come from the copy as digit strings; no maths here.
  // The loader resolves every serial date to one reading (dd/mm/yyyy); anything left is text typed in the Sheet ("da tt").
  const curDay = (cur, t) => cur.event_date ? dateText(cur.event_date) : sheetDay(t.raw_date);
  // NHAP-NHANH-01: dòng vừa sửa còn đang ghi nền (`saving` do bản vá đặt) — Thành tiền chờ số máy chủ, trang không tự tính.
  const savingCell = () => '<td class="num is-saving" title="Đang lưu, chờ máy chủ tính">…</td>';
  const countedCell = (cur, saving = false) => (saving ? savingCell()
    : num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd)));
  // KHOA-CHU-01 (1/11/2026): tháng khóa vẫn sửa được bốn ô chữ (hãng tàu, shipper, nơi đi, nơi đến); container, ngày, tiền, xóa thì không.
  const legacyLocked = (trip, cur, t, stt, unitText) => [cell(stt || '–'), cell(cur.container || 'Phí lẻ'),
    infoCell('legacy', trip.id, 'carrier', cur.carrier ?? ''), shipperCell(infoCell('legacy', trip.id, 'shipper', cur.shipper ?? '')),
    cell(curDay(cur, t)), route(infoCell('legacy', trip.id, 'origin', cur.origin ?? ''), infoCell('legacy', trip.id, 'destination', cur.destination ?? '')),
    num(unitText[0]), feeCells(`legacy:${trip.id}`, cur.container || 'phí lẻ', trip.fee_lines, false), countedCell(cur, trip.saving)].join('');
  const legacyEditable = (trip, cur, t, stt, unitText) => {
    const what = cur.container || 'phí lẻ';
    const edit = (field, text, classes) => infoCell('legacy', trip.id, field, text, classes);
    return [deleteCell('legacy', trip.id, stt || '–', `dòng sổ gốc ${what}`, feePick(`legacy:${trip.id}`, what, cur.unit_price_vnd != null)),
      edit('container', cur.container || 'Phí lẻ'), edit('carrier', cur.carrier ?? ''), shipperCell(edit('shipper', cur.shipper ?? '')),
      edit('event_date', curDay(cur, t)), route(edit('origin', cur.origin ?? ''), edit('destination', cur.destination ?? '')),
      edit('unit_price_vnd', unitText[0], `num ${unitText[1]}`), feeCells(`legacy:${trip.id}`, what, trip.fee_lines, cur.unit_price_vnd != null),
      countedCell(cur, trip.saving)].join('');
  };
  const legacySheet = (trip, t, stt) => [cell(stt), cell(t.container || 'Phí lẻ'), cell(t.carrier ?? ''), shipperCell(cell(t.shipper ?? '')),
    cell(t.date ? dateText(t.date) : sheetDay(t.raw_date)), routeText(t.from ?? '', t.to ?? ''),
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
    // KHOA-CHU-01: tháng khóa chỉ mở bốn ô chữ; chuyến đã loại thì không sửa gì.
    const text = field => (locked && trip && trip.status !== 'rejected' ? infoCell('trip', trip.id, field, trip[field] ?? '') : cell(trip?.[field] ?? ''));
    const infoCells = info
      ? ['container', 'carrier', ...(columns.shipper() ? ['shipper'] : []), 'event_date'].map(field =>
        infoCell('trip', trip.id, field, field === 'event_date' ? dateText(trip.event_date) : trip[field] ?? '')).join('') + route(infoCell('trip', trip.id, 'origin', trip.origin ?? ''), infoCell('trip', trip.id, 'destination', trip.destination ?? ''))
      : `${cell(trip?.container ?? '')}${text('carrier')}${shipperCell(text('shipper'))}${cell(dateText(trip?.event_date))}`
        + route(text('origin').replace(/^<td/, '<span').replace(/<\/td>$/, '</span>'), text('destination').replace(/^<td/, '<span').replace(/<\/td>$/, '</span>'));
    const rowKey = trip ? `trip-${trip.id}` : '';
    const feeEditable = !locked && trip?.editable === true && trip.status === 'confirmed';
    const what = trip?.container || 'phí lẻ';
    const number = sttBase + index + 1;
    const stt = info ? deleteCell('trip', trip.id, trip.is_fee_only ? '–' : number, `chuyến ${what}`, feePick(`trip:${trip.id}`, what, feeEditable))
      : trip && !trip.is_fee_only ? cell(number) : empty();
    const priceText = trip?.is_missing_price ? ['Chuyến đồng bộ', 'Chuyến bộ đồng bộ'].includes(trip.note) ? '' : 'chưa có giá' : fmt(trip?.unit_price_vnd);
    const price = pending || trip?.status === 'rejected' || locked ? num(priceText)
      : trip ? `<td class="num editable ${trip.is_missing_price ? 'missing' : ''}" data-trip="${trip.id}" data-field="unit_price_vnd" tabindex="0" `
        + `role="button" aria-label="Sửa đơn giá chuyến ${index + 1}">${priceText}</td>` : empty('num');
    // SO-GON-04 (L5): trạng thái dòng là nhãn chữ có nền màu ở cột Thành tiền — "chờ kiểm" bấm mở dòng kết luận, "đã loại" gạch.
    const amount = !trip ? empty('num') : pending && locked ? '<td class="num"><span class="row-tag review">chờ kiểm</span></td>'
      : pending ? `<td class="num review-cell"><button type="button" class="review-open row-tag review" data-trip="${trip.id}" aria-expanded="false" `
        + `aria-label="Kết luận chuyến ${escape(trip.container)} đang chờ kiểm">chờ kiểm</button></td>`
      : trip.status === 'rejected' ? '<td class="num"><span class="trip-rejected row-tag rejected">đã loại</span></td>'
        : trip.saving ? savingCell() : num(fmt(trip.amount_vnd));
    return `<tr${rowKey ? ` data-row="${rowKey}"` : ''}${moved.has(rowKey) ? ' class="moved"' : ''}>${stt}
            ${infoCells}
            ${price}
            ${trip ? feeCells(`trip:${trip.id}`, what, trip.fee_lines, feeEditable) : feeEmpty()}
            ${amount}
            </tr>${movedTag(rowKey)}`;
  }

  // Chuyến Sheet chưa vào sổ: CHỜ DUYỆT (dòng mới) hoặc KHÁC (lệch chưa nối được dòng nào trong sổ).
  // DUYET-TAI-HANG-01: máy tự duyệt chuyến mới chắc chắn (v7_inbox._auto_trips); hàng còn lại ghi vì sao máy chưa duyệt
  // và có nút Duyệt ngay ở cột Thành tiền. Ngày sau hôm nay thì không có nút (máy chặn FUTURE_DATE), tới ngày máy tự duyệt.
  const todayVn = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  // Câu ngắn vì sao máy chưa tự duyệt (cùng điều kiện với _auto_trips); câu đủ ở chữ rê chuột.
  const newWhy = (row, today) => String(row.event_date ?? '') > today ? ['Ngày sau hôm nay', 'Tới ngày máy tự duyệt; chưa duyệt tay được.']
    : row.book_match === 'COMMODITY_UNKNOWN' ? ['Sheet chưa ghi mặt hàng', 'Máy chỉ tự duyệt khi mặt hàng trên Sheet khớp sổ. Đúng khách này thì bấm Duyệt.']
      : row.book_match === 'COMMODITY_MISMATCH' ? [`Sheet ghi ${row.commodity ?? 'mặt hàng khác'}`, 'Mặt hàng trên Sheet khác sổ này. Chỉ duyệt khi chắc chuyến thuộc sổ này.']
        : row.book_match === 'COMMODITY_OK' ? ['Tháng cũ đang khóa', 'Máy không tự thêm chuyến vào tháng khóa trước 10/2026. Bấm Duyệt nếu đúng.']
          : ['Chưa chắc sổ này', 'Máy chưa chắc chuyến thuộc sổ này. Đúng khách này thì bấm Duyệt.'];
  const sheetPendingRows = rows => {
    const today = todayVn();
    return rows.map(row => {
      const isNew = row.sync_state === 'NEW';
      const waiting = row.sync_state === 'WAITING';
      const canApprove = isNew && row.source_row != null && String(row.event_date ?? '') <= today;
      const tag = isNew ? `<small class="sheet-tag">CHỜ DUYỆT</small><small class="sheet-why" title="${escape(newWhy(row, today)[1])}">${escape(newWhy(row, today)[0])}</small>`
        : waiting ? `<small class="sheet-tag">CHỜ TAB SHEET</small><small class="sheet-why" title="${escape(WAITING_WHY)}">Không cần làm gì</small>`
          : `<small class="sheet-tag">KHÁC: ${conflictFields(row)}</small>`;
      const act = canApprove ? `<td class="num sheet-new-act"><button type="button" class="sheet-row-approve" data-source-row="${escape(row.source_row)}" `
        + `aria-label="Duyệt chuyến ${escape(row.container)} ngày ${escape(dateText(row.event_date))}">Duyệt</button></td>` : num('–');
      return `<tr class="${isNew ? 'sheet-new' : waiting ? 'sheet-waiting' : 'sheet-conflict'}"${isNew && row.source_row != null ? ` data-sheet-new="${escape(row.source_row)}"` : ''}>
          ${empty()}<td>${escape(row.container)}${tag}</td>`
        + `${cell(row.carrier)}${shipperCell(cell(row.shipper))}${cell(dateText(row.event_date))}${routeText(row.origin, row.destination)}
          ${empty('num')}${feeEmpty()}${act}
          </tr>`;
    }).join('');
  };

  // Dòng trong sổ mà Sheet có dữ liệu khác: tô KHÁC và nút Xem (khung đối chiếu ở so-khach-v7-sheet-ui.js).
  function conflictsAfterRender(data) {
    const sheetRows = data.sheet_sync?.items ?? [];
    for (const row of sheetRows.filter(item => item.sync_state === 'CONFLICT' && item.existing_id)) {
      const target = root.querySelector(`[data-row="${row.existing_kind}-${row.existing_id}"]`);
      if (target) {
        target.classList.add('sheet-conflict');
        target.title = 'Chuyến Sheet có dữ liệu khác. Giữ nguyên sổ hiện có.';
        const label = document.createElement('small'); label.className = 'sheet-tag'; label.textContent = `KHÁC: ${conflictFields(row)}`;
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
