/* Sổ khách V7 bản live — Lịch sử thay đổi: diễn giải từng sự kiện thành câu tiếng Việt.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (xem so-khach-v7-ui.js). */
(window.SoKhachV7LiveParts ??= {}).history = ctx => {
  'use strict';
  const { dateText, fmt, monthKey, monthLabel, model } = ctx;
    const eventLabels = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
      adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi thu', receipt_edit: 'Sửa thông tin phiếu', month_lock: 'Mở/khóa tháng',
      void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu', trip_review: 'Kết luận CHỜ KIỂM',
      trip_edit: 'Sửa ô chuyến', trip_delete: 'Xóa chuyến', legacy_edit: 'Sửa dòng sổ gốc', legacy_delete: 'Xóa dòng sổ gốc',
      sheet_conflict_resolved: 'Đối chiếu Sheet', fee_migration: 'Tách phụ phí',
      add_trip_fees: 'Thêm phụ phí', set_trip_fee_type: 'Sửa phụ phí', replace_trip_fee: 'Sửa khoản phụ phí',
      void_trip_fee: 'Xóa khoản phụ phí', set_book_fee_columns: 'Đổi cột phụ phí riêng',
      receipt_image: 'Đính ảnh chứng từ', receipt_image_remove: 'Gỡ ảnh chứng từ', adjust_month_delete: 'Xóa điều chỉnh cả tháng' };
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
      const parts = [`${who} · ${{ origin: 'Nơi đi', destination: 'Nơi đến' }[field] ?? valueLabels[field] ?? 'Ô'}: ${cellText(field, before.value)} → ${cellText(field, after.value)}`];
      const from = legacy ? before.month : event.after?.moved_from_month, to = legacy ? after.month : event.after?.moved_to_month;
      if (from && to && monthKey(from) !== monthKey(to)) parts.push(`Chuyển tháng ${monthLabel(monthKey(from))} → ${monthLabel(monthKey(to))}`);
      if (legacy && before.counted_vnd !== after.counted_vnd) parts.push(`Số tính: ${fmt(before.counted_vnd)} → ${fmt(after.counted_vnd)}`);
      if (event.after?.review_reason) parts.push(`CHỜ KIỂM: ${reviewReasonText[event.after.review_reason] ?? 'Nghi trùng'}`);
      return parts.join(' · ');
    }
    const valueLabels = { amount_vnd: 'Số tiền', old_amount_vnd: 'Thành tiền trước', new_amount_vnd: 'Thành tiền sau',
      delta_vnd: 'Điều chỉnh', unit_price_vnd: 'Đơn giá', other_fee_vnd: 'Phụ phí', new_value_vnd: 'Giá trị mới',
      date: 'Ngày trả', event_date: 'Ngày chuyến', month: 'Tháng', debt_month: 'Tháng', pid: 'Phiếu',
      reference: 'Tham chiếu', method: 'Hình thức', container: 'Container', carrier: 'Hãng tàu', from: 'Nơi đi', to: 'Nơi đến',
      counterparty_name: 'Sổ bên kia', void_reason: 'Lý do hủy',
      unitPriceVnd: 'Đơn giá', otherFeeVnd: 'Phụ phí', openings: 'Số kỳ số dư đầu', legacy: 'Số dòng lịch sử' };
    function describe(value, kind) {
      if (!value || typeof value !== 'object') return 'Chưa có';
      const parts = [];
      for (const [name, item] of Object.entries(value)) {
        if (kind === 'paste' && name === 'date' && Object.hasOwn(value, 'event_date')) continue;
        if (name === 'price') parts.push(describe(item, kind));
        else if (name === 'trips' && Array.isArray(item)) parts.push(`Chuyến: ${item.map(trip => describe(trip, kind)).join('; ') || 'Chưa có'}`);
        else if (name === 'allocations' && Array.isArray(item)) parts.push(`Phân bổ: ${item.map(line =>
          `tháng ${monthLabel(monthKey(line.month))} · ${line.kind === 'advance' ? 'Ứng trước' : 'Trừ nợ'} · ${fmt(line.amount_vnd)}`).join('; ') || 'Không có'}`);
        else if (Object.hasOwn(valueLabels, name) && (item === null || typeof item !== 'object')) {
          const text = name.endsWith('_vnd') || name.endsWith('Vnd') ? fmt(item)
            : ['date', 'event_date'].includes(name) ? dateText(item)
              : ['month', 'debt_month'].includes(name) ? monthLabel(monthKey(item)) : item;
          const label = name === 'new_value_vnd'
            ? value.field === 'unit_price_vnd' ? 'Đơn giá' : value.field === 'other_fee_vnd' ? 'Phụ phí' : valueLabels[name]
            : name === 'date' && kind === 'paste' ? 'Ngày chuyến' : valueLabels[name];
          parts.push(`${label}: ${text ?? '–'}`);
        }
      }
      return parts.join(' · ') || 'Chưa có';
    }
    function describeEvent(event) {
      if (event.kind === 'sheet_conflict_resolved') {
        const before = event.before ?? {}, after = event.after ?? {};
        const label = { carrier: 'Hãng tàu', shipper: 'Shipper', origin: 'Điểm đi', destination: 'Điểm đến' }[after.field] ?? 'Ô';
        return `${label}: ${cellText(after.field, before.value)} → ${cellText(after.field, after.target_value)} · ${after.decision === 'use_sheet' ? 'Lấy Sheet' : 'Giữ web'}`;
      }
      // CHUNG-TU-01: ảnh không đổi tiền, chỉ ghi phiếu nào và lý do gỡ.
      if (event.kind === 'receipt_image') return `Phiếu ${event.after?.image?.pid ?? '–'} · thêm 1 ảnh`;
      if (event.kind === 'receipt_image_remove') return `Phiếu ${event.after?.image?.pid ?? '–'} · gỡ 1 ảnh · Lý do: ${event.after?.image?.reason ?? '–'}`;
      if (event.kind === 'adjust_month_delete') {
        const old = event.before?.adjustment ?? {};
        return `Tháng ${monthLabel(monthKey(old.month))}: ${fmt(old.amount_vnd)}${old.note ? ` (${old.note})` : ''} → 0`;
      }
      if (['add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns'].includes(event.kind)) return describeFeeEvent(event);
      if (event.kind === 'month_lock') return `${event.after?.locked ? 'Khóa' : 'Mở'} tháng ${monthLabel(monthKey(event.after?.month))}`;
      if (event.kind === 'trip_review') return `Chuyến ${event.after?.container || '–'}: ${event.after?.status === 'confirmed'
        ? 'tính vào sổ' : 'loại, không tính'}`;
      if (['trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete'].includes(event.kind)) return describeCellEvent(event);
      if (event.kind !== 'adjust_trip') return `${describe(event.before, event.kind)} → ${describe(event.after, event.kind)}`;
      const before = event.before ?? {}, after = event.after ?? {};
      const field = after.field ?? before.field;
      const fieldLabel = field === 'unit_price_vnd' ? 'Đơn giá' : field === 'other_fee_vnd' ? 'Phụ phí' : null;
      const parts = fieldLabel ? [`${fieldLabel}: ${fmt(before.new_value_vnd)} → ${fmt(after.new_value_vnd)}`] : [];
      parts.push(`Thành tiền: ${fmt(before.amount_vnd ?? after.old_amount_vnd)} → ${fmt(after.new_amount_vnd)}`);
      const delta = fmt(after.delta_vnd);
      parts.push(`Điều chỉnh: ${/^[0-9]/.test(delta) ? '+' : ''}${delta}`);
      return parts.join(' · ');
    }
    function eventTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return 'Chưa rõ thời điểm';
      const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh',
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date);
      const part = name => parts.find(item => item.type === name).value;
      return `${part('day')}/${part('month')}/${part('year')} ${part('hour')}:${part('minute')}`;
    }
    Object.assign(ctx, { eventLabels, reviewReasonText, describeEvent, eventTime });
};
