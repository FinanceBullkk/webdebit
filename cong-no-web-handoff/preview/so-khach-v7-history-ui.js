/* Sổ khách V7 bản live — Lịch sử thay đổi: mỗi sự kiện một dòng "giờ · người làm · câu", ghi chú/lý do chỉ hiện khi có,
 * lọc theo loại (SO-GON-04, L6). Người làm là tên ngắn server gắn theo bảng tên của PRESENCE-01 (`actor_name`), không phải login.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).history = ctx => {
  'use strict';
  const { root, escape, dateText, fmt, monthKey, monthLabel, model } = ctx;
    const eventLabels = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
      adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi phiếu thu', receipt_edit: 'Sửa thông tin phiếu', month_lock: 'Mở/khóa tháng',
      void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu', trip_review: 'Kết luận CHỜ KIỂM',
      trip_edit: 'Sửa ô chuyến', trip_delete: 'Xóa chuyến', legacy_edit: 'Sửa dòng sổ gốc', legacy_delete: 'Xóa dòng sổ gốc',
      sheet_conflict_resolved: 'Đối chiếu Sheet', fee_migration: 'Tách phụ phí',
      add_trip_fees: 'Thêm phụ phí', set_trip_fee_type: 'Sửa phụ phí', replace_trip_fee: 'Sửa khoản phụ phí',
      void_trip_fee: 'Xóa khoản phụ phí', set_book_fee_columns: 'Đổi cột phụ phí riêng', rewrite_trip_fees: 'Tách phụ phí theo PS',
      receipt_image: 'Đính ảnh chứng từ', receipt_image_remove: 'Gỡ ảnh chứng từ',
      price_table_edit: 'Sửa bảng giá', price_table_apply: 'Điền giá theo bảng',
      adjust_month_delete: 'Xóa điều chỉnh cả tháng' };
    const counterparty = event => event.counterparty_name ?? event.after?.counterparty_name;
    const labelOf = event => event.kind === 'month_lock' && typeof event.after?.locked === 'boolean' ? event.after.locked ? 'Khóa tháng' : 'Mở khóa tháng'
      : event.kind === 'receipt' && counterparty(event) != null ? 'Cấn trừ'
        : Object.hasOwn(eventLabels, event.kind) ? eventLabels[event.kind] : 'Thao tác khác';
    // Lọc theo loại: Thu · Chuyến · Giá/phụ phí · Khóa tháng · Tất cả. Nhập số dư đầu và thao tác lạ chỉ ở Tất cả.
    const GROUPS = [['thu', 'Thu'], ['chuyen', 'Chuyến'], ['gia', 'Giá/phụ phí'], ['khoa', 'Khóa tháng'], ['all', 'Tất cả']];
    const FEE_KINDS = ['add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns', 'rewrite_trip_fees'];
    const kindGroups = { thu: ['receipt', 'receipt_edit', 'void', 'reallocation', 'receipt_image', 'receipt_image_remove'],
      chuyen: ['paste', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete', 'trip_review', 'sheet_conflict_resolved'],
      gia: ['price_edit', 'adjust_trip', 'adjust_month', 'adjust_month_delete', 'price_table_edit', 'price_table_apply', 'fee_migration', ...FEE_KINDS],
      khoa: ['month_lock'] };
    function groupOf(event) {
      // Dòng sổ gốc: khoản thu thuộc Thu, sửa đơn giá/phụ phí thuộc Giá/phụ phí.
      const legacy = event.before?.legacy;
      if (['legacy_edit', 'legacy_delete'].includes(event.kind) && legacy?.kind === 'receipt') return 'thu';
      if (event.kind === 'legacy_edit' && ['unit_price_vnd', 'other_fee_vnd'].includes(legacy?.field)) return 'gia';
      return Object.keys(kindGroups).find(group => kindGroups[group].includes(event.kind)) ?? '';
    }
    const containerOf = id => id == null ? '' : (ctx.snapshot?.trips ?? []).find(trip => String(trip.id) === String(id))?.container || `#${id}`;
    const receiptOf = id => (ctx.snapshot?.receipts ?? []).find(item => String(item.id) === String(id));
    const day = value => dateText(value) || '–';
    const signed = value => { const text = fmt(value); return /^[0-9]/.test(text) ? `+${text}` : text; };
    // Phân bổ của phiếu: "trừ T8 1.000.000 · T9 199.000.000; ứng trước T10 5.000.000" (tháng khác năm của phiếu ghi thêm năm).
    const monthShort = (value, year) => { const key = monthKey(value); return key ? `T${Number(key.slice(5))}${key.slice(0, 4) === year ? '' : `/${key.slice(0, 4)}`}` : '–'; };
    function allocText(lines, year) {
      const list = Array.isArray(lines) ? lines : [];
      const part = (advance, word) => {
        const items = list.filter(line => (line?.kind === 'advance') === advance).map(line => `${monthShort(line.month, year)} ${fmt(line.amount_vnd)}`);
        return items.length ? `${word} ${items.join(' · ')}` : '';
      };
      return [part(false, 'trừ'), part(true, 'ứng trước')].filter(Boolean).join('; ');
    }
    // PHU-PHI-01: lệnh phụ phí ghi {targets: [{trip_id|legacy_row_id, fee_lines, counted_vnd}], batch_count} trước → sau.
    const feeTargetName = target => {
      const snapshot = ctx.snapshot;
      const row = target.trip_id != null ? (snapshot?.trips ?? []).find(trip => trip.id === Number(target.trip_id))
        : (snapshot?.legacy_rows ?? []).find(item => item.id === Number(target.legacy_row_id));
      return (target.trip_id != null ? row?.container : row?.current?.container) || `#${target.trip_id ?? target.legacy_row_id}`;
    };
    const feeTotalText = lines => { const total = model.feeCells(lines ?? [], []).totalVnd; return total === null ? '–' : model.formatVnd(total); };
    function describeFeeEvent(event) {
      if (event.kind === 'set_book_fee_columns') {
        const names = list => (list ?? []).map(item => ctx.feeTypeName(item?.fee_type_id ?? item)).join(', ') || 'chỉ Khác';
        return `Cột riêng: ${names(event.before?.fee_columns)} → ${names(event.after?.fee_columns)}`;
      }
      const before = event.before?.targets ?? [], after = event.after?.targets ?? [];
      const parts = after.slice(0, 5).map((target, index) => {
        const old = before[index] ?? {};
        const added = (target.fee_lines ?? []).filter(line => line.id == null)
          .map(line => `${ctx.feeTypeName(line.fee_type_id)} ${fmt(line.amount_vnd)}${line.note ? ` (${line.note})` : ''}`);
        const counted = target.legacy_row_id != null && old.counted_vnd != null && old.counted_vnd !== target.counted_vnd
          ? ` · Thành tiền: ${fmt(old.counted_vnd)} → ${fmt(target.counted_vnd)}` : '';
        return `${feeTargetName(target)}: phụ phí ${feeTotalText(old.fee_lines)} → ${feeTotalText(target.fee_lines)}${added.length ? ` (${added.join(', ')})` : ''}${counted}`;
      });
      const count = event.after?.batch_count ?? after.length;
      return `${count > 1 ? `${count} chuyến · ` : ''}${parts.join(' · ')}${after.length > 5 ? ` · và ${after.length - 5} chuyến khác` : ''}`;
    }
    const reviewReasonText = { BASELINE_CODE_MATCH: 'Trùng mã với dòng sổ gốc', BASELINE_DATE_WINDOW: 'Cùng container, lệch ngày ≤3 ngày với dòng sổ gốc',
      WEB_DUPLICATE: 'Trùng chuyến đã nhập trên web', BATCH_DUPLICATE: 'Trùng trong cùng lô dán' };
    const fieldLabels = { container: 'Container', carrier: 'Hãng tàu', shipper: 'Shipper', event_date: 'Ngày chuyến', origin: 'Nơi đi',
      destination: 'Nơi đến', unit_price_vnd: 'Đơn giá', other_fee_vnd: 'Phụ phí' };
    const cellText = (field, value) => value === null || value === undefined || value === '' ? '–'
      : field === 'event_date' ? dateText(value) : field.endsWith('_vnd') ? fmt(value) : String(value);
    // Một ô trước → sau, kèm chuyển tháng và số tính của dòng sổ gốc nếu đổi.
    function describeCellEvent(event) {
      const legacy = event.kind.startsWith('legacy');
      const before = (legacy ? event.before?.legacy : event.before?.trip) ?? {};
      const after = (legacy ? event.after?.legacy : event.after?.trip) ?? {};
      // Sự kiện sửa ô chuyến web chỉ mang id: lấy container từ sổ đang xem (chuyến đã xóa có ảnh đủ ở `before`).
      const known = legacy ? null : (ctx.snapshot?.trips ?? []).find(row => String(row.id) === String(before.id ?? after.id));
      const paid = before.kind === 'receipt';
      const who = `${paid ? 'Khoản thu sổ gốc' : legacy ? 'Dòng sổ gốc' : 'Chuyến'} ${before.container || after.container || known?.container || '–'}`;
      if (event.kind.endsWith('_delete')) {
        const amount = legacy ? before.counted_vnd : before.amount_vnd;
        if (paid) return `${who} · tháng ${monthLabel(monthKey(before.month ?? before.debt_month))} · Số đã trừ nợ: ${fmt(amount)}`;
        return `${who} · ${cellText('event_date', before.event_date)} · tháng ${monthLabel(monthKey(before.month ?? before.debt_month))} · ${legacy ? 'Số đang tính' : 'Thành tiền'}: ${fmt(amount)}`;
      }
      const field = after.field ?? before.field;
      const parts = [`${who} · ${fieldLabels[field] ?? 'Ô'}: ${cellText(field, before.value)} → ${cellText(field, after.value)}`];
      const from = legacy ? before.month : event.after?.moved_from_month, to = legacy ? after.month : event.after?.moved_to_month;
      if (from && to && monthKey(from) !== monthKey(to)) parts.push(`Chuyển tháng ${monthLabel(monthKey(from))} → ${monthLabel(monthKey(to))}`);
      if (legacy && before.counted_vnd !== after.counted_vnd) parts.push(`Số tính: ${fmt(before.counted_vnd)} → ${fmt(after.counted_vnd)}`);
      if (event.after?.review_reason) parts.push(`CHỜ KIỂM: ${reviewReasonText[event.after.review_reason] ?? 'Nghi trùng'}`);
      return parts.join(' · ');
    }
    // Phiếu thu: "PH-012: 200.000.000 đ ngày 15/10/2026 · THU TIỀN (trừ T8 1.000.000 · T9 199.000.000)".
    function receiptText(event) {
      const after = event.after ?? {};
      const head = [after.pid, `${fmt(after.amount_vnd)} đ ngày ${day(after.date)}`].filter(Boolean).join(': ');
      if (counterparty(event) != null) return `${head} · sổ bên kia ${counterparty(event)}`;
      const alloc = allocText(after.allocations, String(after.date ?? '').slice(0, 4));
      return `${head}${after.method ? ` · ${after.method}` : ''}${after.reference ? ` · tham chiếu ${after.reference}` : ''}${alloc ? ` (${alloc})` : ''}`;
    }
    const metaFields = [['date', 'ngày', day], ['method', 'hình thức', String], ['reference', 'tham chiếu', String]];
    function receiptEditText(event) {
      const before = event.before ?? {}, after = event.after ?? {};
      const show = (value, format) => value === null || value === undefined || value === '' ? '–' : format(value);
      const changes = metaFields.filter(([field]) => Object.hasOwn(after, field) && (before[field] ?? '') !== (after[field] ?? ''))
        .map(([field, word, format]) => `${word} ${show(before[field], format)} → ${show(after[field], format)}`);
      return `${after.pid ?? before.pid ?? ''}: ${changes.join(' · ') || 'không đổi'}`;
    }
    function priceText(event) {
      const before = event.before?.price ?? {}, after = event.after?.price ?? {};
      const name = containerOf(after.trip_id ?? before.trip_id);
      const parts = [['unit_price_vnd', 'Đơn giá'], ['other_fee_vnd', 'Phụ phí']].filter(([field]) => (before[field] ?? null) !== (after[field] ?? null))
        .map(([field, label]) => `${label}: ${fmt(before[field])} → ${fmt(after[field])}`);
      return `${name ? `Chuyến ${name} · ` : ''}${parts.join(' · ') || `Đơn giá: ${fmt(after.unit_price_vnd)}`}`;
    }
    function pasteText(event) {
      const trips = Array.isArray(event.after?.trips) ? event.after.trips : [];
      const items = trips.slice(0, 5).map(trip => `${trip.container || 'phí lẻ'} (${trip.event_date ? dateText(trip.event_date) : trip.date || 'không ngày'}`
        + `${trip.unitPriceVnd ? `, ${fmt(trip.unitPriceVnd)}` : ''})`);
      const review = trips.filter(trip => trip.status === 'pending_review').length;
      return `${trips.length} chuyến: ${items.join(' · ')}${trips.length > 5 ? ` · và ${trips.length - 5} chuyến khác` : ''}${review ? ` · ${review} chuyến chờ kiểm` : ''}`;
    }
    function adjustTripText(event) {
      const before = event.before ?? {}, after = event.after ?? {};
      const field = after.field ?? before.field;
      const fieldLabel = field === 'unit_price_vnd' ? 'Đơn giá' : field === 'other_fee_vnd' ? 'Phụ phí' : null;
      const parts = [`Chuyến ${containerOf(before.trip ?? after.trip_id) || '–'}`];
      if (fieldLabel) parts.push(`${fieldLabel}: ${fmt(before.new_value_vnd)} → ${fmt(after.new_value_vnd)}`);
      parts.push(`Thành tiền: ${fmt(before.amount_vnd ?? after.old_amount_vnd)} → ${fmt(after.new_amount_vnd)}`, `Điều chỉnh: ${signed(after.delta_vnd)}`);
      return parts.join(' · ');
    }
    // Câu đi sau tên thao tác; thao tác lạ không có câu (không lộ mã hay khóa JSON).
    function describeEvent(event) {
      const before = event.before ?? {}, after = event.after ?? {};
      if (event.kind === 'sheet_conflict_resolved') {
        const label = { carrier: 'Hãng tàu', shipper: 'Shipper', origin: 'Điểm đi', destination: 'Điểm đến' }[after.field] ?? 'Ô';
        return `${label}: ${cellText(after.field, before.value)} → ${cellText(after.field, after.target_value)} · ${after.decision === 'use_sheet' ? 'Lấy Sheet' : 'Giữ web'}`;
      }
      // BANG-GIA-01: sửa bảng giá ghi cả bảng trước → sau; áp giá ghi từng chuyến {container, unit_price_vnd} trước → sau.
      if (event.kind === 'price_table_edit') {
        const size = table => `${(table?.periods ?? []).length} đợt, ${(table?.locations ?? []).length} kho, ${(table?.tt_shippers ?? []).length} shipper TT`;
        return `Bảng giá: ${size(before.price_table)} → ${size(after.price_table)}`;
      }
      if (event.kind === 'price_table_apply') {
        const old = before.trips ?? [], trips = after.trips ?? [];
        const parts = trips.slice(0, 5).map((trip, index) => `${trip.container || `#${trip.trip_id}`}: ${fmt(old[index]?.unit_price_vnd)} → ${fmt(trip.unit_price_vnd)}`);
        return `${trips.length} chuyến · ${parts.join(' · ')}${trips.length > 5 ? ` · và ${trips.length - 5} chuyến khác` : ''}`;
      }
      // CHUNG-TU-01: ảnh không đổi tiền, chỉ ghi phiếu nào (lý do gỡ ở dòng lý do).
      if (event.kind === 'receipt_image' || event.kind === 'receipt_image_remove') return `phiếu ${after.image?.pid ?? '–'}`;
      if (event.kind === 'adjust_month_delete') {
        const old = before.adjustment ?? {};
        return `${monthLabel(monthKey(old.month))}: ${fmt(old.amount_vnd)}${old.note ? ` (${old.note})` : ''} → 0`;
      }
      if (FEE_KINDS.includes(event.kind)) return describeFeeEvent(event);
      if (event.kind === 'month_lock') return monthLabel(monthKey(after.month));
      if (event.kind === 'trip_review') return `chuyến ${after.container || '–'}: ${after.status === 'confirmed' ? 'tính vào sổ' : 'loại, không tính'}`;
      if (['trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete'].includes(event.kind)) return describeCellEvent(event);
      if (event.kind === 'receipt') return receiptText(event);
      if (event.kind === 'receipt_edit') return receiptEditText(event);
      if (event.kind === 'void') return [before.pid ?? after.pid, before.amount_vnd == null ? '' : `${fmt(before.amount_vnd)} đ`].filter(Boolean).join(': ');
      if (event.kind === 'reallocation') {
        const id = after.receipt ?? before.receipt, year = String(receiptOf(id)?.date ?? '').slice(0, 4);
        return `phiếu ${receiptOf(id)?.pid ?? `#${id ?? '–'}`}: ${allocText(before.allocations, year) || 'chưa trừ'} → ${allocText(after.allocations, year) || 'chưa trừ'}`;
      }
      if (event.kind === 'import') return `${after.openings ?? 0} kỳ số dư đầu, ${after.legacy ?? 0} dòng sổ gốc`;
      if (event.kind === 'adjust_month') return `${monthLabel(monthKey(after.month))}: ${signed(after.amount_vnd)}`;
      if (event.kind === 'adjust_trip') return adjustTripText(event);
      if (event.kind === 'price_edit') return priceText(event);
      if (event.kind === 'paste') return pasteText(event);
      return '';
    }
    // Ghi chú hoặc lý do người làm gõ; không có thì không hiện dòng nào.
    function noteOf(event) {
      const after = event.after ?? {};
      if (event.kind === 'void' && after.void_reason) return `Lý do hủy: ${after.void_reason}`;
      if (event.kind === 'trip_review' && after.review_reason) return `Lý do: ${after.review_reason}`;
      if (event.kind === 'receipt_image_remove' && after.image?.reason) return `Lý do gỡ: ${after.image.reason}`;
      const tripNotes = Array.isArray(after.trips) ? after.trips.map(trip => trip?.note).filter(Boolean).join('; ') : '';
      const note = after.note || tripNotes || event.before?.note;
      return note ? `Ghi chú: ${note}` : '';
    }
    function eventTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return 'Chưa rõ thời điểm';
      const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh',
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date);
      const part = name => parts.find(item => item.type === name).value;
      return `${part('day')}/${part('month')}/${part('year')} ${part('hour')}:${part('minute')}`;
    }
    // PRESENCE-01: tên ngắn server gắn; sổ đọc từ bản API cũ chưa có `actor_name` thì lấy phần trước @ như server.
    const actorName = event => String(event.actor_name || String(event.actor ?? '').split('@')[0] || 'Chưa rõ người làm').slice(0, 40);
    // Khung Lịch sử (nút "Lịch sử" ở đầu sổ). Bộ lọc giữ qua các lần vẽ lại; bấm lọc chỉ đổi thuộc tính, không vẽ lại sổ.
    let filter = 'all';
    function historyList(events) {
      if (!events.length) return '<p>Chưa có thay đổi nào</p>';
      const groups = events.map(groupOf);
      const count = key => key === 'all' ? events.length : groups.filter(group => group === key).length;
      const buttons = GROUPS.map(([key, label]) => `<button type="button" data-filter="${key}" aria-pressed="${key === filter}">${label} (${count(key)})</button>`).join('');
      const items = events.map((event, index) => {
        const text = describeEvent(event), note = noteOf(event);
        return `<li data-group="${groups[index]}"><time>${escape(eventTime(event.at))}</time> · <span class="who">${escape(actorName(event))}</span> · `
          + `<strong>${escape(labelOf(event))}</strong>${text ? ` ${escape(text)}` : ''}${note ? `<small>${escape(note)}</small>` : ''}</li>`;
      }).join('');
      return `<div class="history-filter" role="group" aria-label="Lọc Lịch sử theo loại">${buttons}</div>`
        + `<ol class="history-items" data-filter="${filter}">${items}</ol><p class="history-none"${count(filter) ? ' hidden' : ''}>Không có thay đổi loại này.</p>`;
    }
    root.addEventListener('click', event => {
      const button = event.target.closest('.history-filter button');
      if (!button) return;
      filter = button.dataset.filter;
      const panel = button.closest('.history-panel');
      panel.querySelector('.history-items').dataset.filter = filter;
      panel.querySelectorAll('.history-filter button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      panel.querySelector('.history-none').hidden = panel.querySelectorAll(filter === 'all' ? '.history-items > li' : `.history-items > li[data-group="${filter}"]`).length > 0;
    });
    Object.assign(ctx, { reviewReasonText, historyList });
};
